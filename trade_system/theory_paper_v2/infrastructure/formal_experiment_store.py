"""Strict input loading and write-once storage for the formal E0 experiment.

This adapter only reads already-frozen input artifacts and persists an
application result.  It never collects data, invokes a model, or creates the
separate second-round 101-percent account.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping

from ..application.formal_experiment import (
    FORMAL_E0_CONTRACT_DIGEST,
    DatasetManifestRef,
    FormalExperimentContract,
    FormalExperimentError,
    FormalExperimentResult,
    PairedObservationReceipt,
)
from ..application.topology_evaluation import TOPOLOGY_IDS
from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)


_MUTABLE_ALIASES = {"current", "latest"}
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_COHORT_ORDER = {
    "TOPOLOGY_SELECTION": 0,
    "POLICY_QUALIFICATION": 1,
    "FORMAL_EXPERIMENT": 2,
}
_DECIMAL_FIELDS = {
    "dynamic_candidate_coverage",
    "material_challenge_coverage",
    "action_quality_score",
    "net_pnl_after_cost",
    "transaction_cost",
    "max_drawdown_fraction",
    "primary_path_capture",
    "frozen_baseline_net_pnl_after_cost",
    "frozen_baseline_max_drawdown_fraction",
    "frozen_baseline_primary_path_capture",
}
_OPTIONAL_DECIMAL_FIELDS = {
    "net_pnl_after_cost",
    "transaction_cost",
    "max_drawdown_fraction",
    "primary_path_capture",
    "frozen_baseline_net_pnl_after_cost",
    "frozen_baseline_max_drawdown_fraction",
    "frozen_baseline_primary_path_capture",
}
_INTEGER_FIELDS = {
    "safety_state_pit_authority_failures",
    "role_overreach_failures",
    "model_calls",
    "tokens",
    "latency_ms",
    "timeout_count",
    "missing_role_count",
    "sample_index",
    "hard_constraint_error_count",
    "state_continuity_error_count",
    "reproducibility_difference_count",
}


class FormalExperimentStoreError(ValueError):
    """A fail-closed frozen-input or write-once storage violation."""


@dataclass(frozen=True, slots=True)
class MaterializedFormalExperiment:
    run_root: Path
    manifest_path: Path
    authority_snapshot_path: Path
    result_path: Path
    markdown_path: Path
    artifact_index_path: Path
    artifact_index_digest: str


def _reject_mutable_path(path: Path) -> None:
    if any(part.casefold() in _MUTABLE_ALIASES for part in path.parts):
        raise FormalExperimentStoreError(
            "MUTABLE_CURRENT_OR_LATEST_INPUT_FORBIDDEN"
        )


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalExperimentStoreError(code)
    return value


def _inclusive_indices(value: object, code: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(item) is not int for item in value)
        or value[0] > value[1]
    ):
        raise FormalExperimentStoreError(code)
    return tuple(range(value[0], value[1] + 1))


def load_formal_experiment_contract(
    path: Path,
) -> FormalExperimentContract:
    """Load only the frozen TA2 formal-E0 contract."""

    source = Path(path)
    _reject_mutable_path(source)
    try:
        value = load_json_strict(source)
        supplied_digest = verify_self_digest(value, "contract_digest")
    except Exception as exc:
        raise FormalExperimentStoreError(
            "FORMAL_EXPERIMENT_CONTRACT_NOT_ADMISSIBLE"
        ) from exc
    sample = _mapping(
        value.get("sample_contract"),
        "FORMAL_SAMPLE_CONTRACT_INVALID",
    )
    topology = _mapping(
        value.get("topology_contract"),
        "FORMAL_TOPOLOGY_CONTRACT_INVALID",
    )
    evaluation = _mapping(
        value.get("evaluation_contract"),
        "FORMAL_EVALUATION_CONTRACT_INVALID",
    )
    advance = _mapping(
        value.get("advance_contract"),
        "FORMAL_ADVANCE_CONTRACT_INVALID",
    )
    data = _mapping(
        value.get("data_contract"),
        "FORMAL_DATA_CONTRACT_INVALID",
    )
    if (
        supplied_digest != FORMAL_E0_CONTRACT_DIGEST
        or value.get("schema_id")
        != "theory_agent_v2_formal_e0_experiment_contract"
        or value.get("schema_version") != "1.0.0"
        or value.get("contract_id") != "TA2-FORMAL-E0-20260731"
        or value.get("frozen_before_first_generative_call") is not True
        or value.get("system_mode") != "E0_OFFLINE_COUNTERFACTUAL"
        or value.get("external_execution_authority") != "NONE_E0"
        or value.get("executable") is not False
        or data.get("source_owner") != "BINANCE"
        or data.get("product") != "USD_M_FUTURES"
        or data.get("symbol") != "BTCUSDT"
        or data.get("base_interval") != "1h"
        or data.get("requested_closed_bar_count") != 256
        or data.get("future_data_disposition") != "HARD_FAIL"
        or tuple(topology.get("topology_ids", ())) != TOPOLOGY_IDS
        or topology.get("minimum_complete_paired_sessions") != 32
        or topology.get("model") != "gpt-5.6-sol"
        or topology.get("reasoning_effort") != "medium"
        or topology.get("provider_transport")
        != "CODEX_EXEC_CHATGPT_LOGIN"
        or topology.get("calls_per_topology_limit") != 3
        or topology.get("total_token_limit_per_topology") != 90_000
        or topology.get("timeout_seconds_per_call") != 120
        or topology.get("tool_policy") != "NO_TOOLS"
        or topology.get("formal_output_requires_usage") is not True
        or topology.get("synthetic_or_mock_disposition")
        != "NOT_FORMAL_EVIDENCE"
        or evaluation.get("topology_interval_method")
        != "PAIRED_HOEFFDING_SCORE_RANGE_MINUS1_PLUS1"
        or evaluation.get("topology_interval_alpha") != "0.05"
        or advance.get("data_quality_required") != "PASS"
        or advance.get("role_transport_contract_required") != "PASS"
        or advance.get("topology_complete_pairs_required") != 32
        or advance.get("equal_model_input_budget_required") is not True
        or advance.get("hard_safety_failures_allowed") != 0
        or advance.get(
            "second_round_101_percent_cost_instantiation_requires_behavior_and_economic_gate"
        )
        is not True
    ):
        raise FormalExperimentStoreError(
            "FORMAL_EXPERIMENT_CONTRACT_MISMATCH"
        )
    try:
        return FormalExperimentContract(
            contract_digest=supplied_digest,
            topology_ids=tuple(topology["topology_ids"]),
            requested_model=str(topology["model"]),
            topology_selection_indices=_inclusive_indices(
                sample.get("topology_selection_indices_inclusive"),
                "FORMAL_TOPOLOGY_SELECTION_RANGE_INVALID",
            ),
            policy_qualification_indices=_inclusive_indices(
                sample.get("policy_qualification_indices_inclusive"),
                "FORMAL_POLICY_QUALIFICATION_RANGE_INVALID",
            ),
            formal_experiment_indices=_inclusive_indices(
                sample.get("formal_experiment_indices_inclusive"),
                "FORMAL_EXPERIMENT_RANGE_INVALID",
            ),
            minimum_complete_paired_sessions=int(
                topology["minimum_complete_paired_sessions"]
            ),
            data_quality_required=str(
                advance["data_quality_required"]
            ),
            role_transport_contract_required=str(
                advance["role_transport_contract_required"]
            ),
            hard_safety_failures_allowed=int(
                advance["hard_safety_failures_allowed"]
            ),
            second_round_requires_behavior_and_economic_gate=bool(
                advance[
                    "second_round_101_percent_cost_instantiation_requires_behavior_and_economic_gate"
                ]
            ),
        )
    except (KeyError, TypeError, ValueError, FormalExperimentError) as exc:
        raise FormalExperimentStoreError(
            "FORMAL_EXPERIMENT_CONTRACT_MISMATCH"
        ) from exc


def load_dataset_manifest_ref(path: Path) -> DatasetManifestRef:
    source = Path(path)
    _reject_mutable_path(source)
    try:
        value = load_json_strict(source)
    except Exception as exc:
        raise FormalExperimentStoreError(
            "DATASET_MANIFEST_REF_NOT_ADMISSIBLE"
        ) from exc
    expected = {item.name for item in fields(DatasetManifestRef)}
    if set(value) != expected or type(value.get("decision_slot_count")) is not int:
        raise FormalExperimentStoreError(
            "DATASET_MANIFEST_REF_SHAPE_INVALID"
        )
    try:
        return DatasetManifestRef(**value)
    except (TypeError, ValueError, FormalExperimentError) as exc:
        raise FormalExperimentStoreError(
            "DATASET_MANIFEST_REF_NOT_ADMISSIBLE"
        ) from exc


def _decimal(value: object, name: str) -> Decimal | None:
    if value is None and name in _OPTIONAL_DECIMAL_FIELDS:
        return None
    if not isinstance(value, str):
        raise FormalExperimentStoreError(
            f"PAIRED_OBSERVATION_DECIMAL_INVALID:{name}"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FormalExperimentStoreError(
            f"PAIRED_OBSERVATION_DECIMAL_INVALID:{name}"
        ) from exc
    if not parsed.is_finite():
        raise FormalExperimentStoreError(
            f"PAIRED_OBSERVATION_DECIMAL_INVALID:{name}"
        )
    return parsed


def load_paired_observation_receipt(
    path: Path,
) -> PairedObservationReceipt:
    source = Path(path)
    _reject_mutable_path(source)
    try:
        value = load_json_strict(source)
    except Exception as exc:
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_NOT_ADMISSIBLE"
        ) from exc
    expected = {item.name for item in fields(PairedObservationReceipt)}
    if set(value) != expected:
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_SHAPE_INVALID"
        )
    converted = dict(value)
    for name in _DECIMAL_FIELDS:
        converted[name] = _decimal(converted[name], name)
    for name in _INTEGER_FIELDS:
        if type(converted[name]) is not int:
            raise FormalExperimentStoreError(
                f"PAIRED_OBSERVATION_INTEGER_INVALID:{name}"
            )
    if (
        converted["cost_microunits"] is not None
        and type(converted["cost_microunits"]) is not int
    ):
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_INTEGER_INVALID:cost_microunits"
        )
    if type(converted["formal_evidence"]) is not bool:
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_FORMAL_FLAG_INVALID"
        )
    raw_output_refs = converted["raw_output_refs"]
    if not isinstance(raw_output_refs, list) or any(
        not isinstance(item, str) for item in raw_output_refs
    ):
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_RAW_OUTPUT_REFS_INVALID"
        )
    converted["raw_output_refs"] = tuple(raw_output_refs)
    if converted["served_model_attestation"] is not None and not isinstance(
        converted["served_model_attestation"], str
    ):
        raise FormalExperimentStoreError(
            "SERVED_MODEL_ATTESTATION_INVALID"
        )
    try:
        return PairedObservationReceipt(**converted)
    except (TypeError, ValueError, FormalExperimentError) as exc:
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_NOT_ADMISSIBLE"
        ) from exc


def load_paired_observation_receipts(
    directory: Path,
) -> tuple[PairedObservationReceipt, ...]:
    source = Path(directory)
    _reject_mutable_path(source)
    if not source.is_dir():
        raise FormalExperimentStoreError(
            "PAIRED_OBSERVATION_DIRECTORY_MISSING"
        )
    paths = tuple(sorted(source.rglob("*.json")))
    if not paths:
        raise FormalExperimentStoreError("FORMAL_PAIRED_EVIDENCE_MISSING")
    return tuple(load_paired_observation_receipt(path) for path in paths)


def _write_once_text(path: Path, text: str) -> None:
    payload = text.encode("utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.read_bytes() != payload:
            raise FormalExperimentStoreError(
                f"WRITE_ONCE_CONFLICT:{target}"
            )
        return
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        if target.is_file() and target.read_bytes() == payload:
            return
        raise FormalExperimentStoreError(
            f"WRITE_ONCE_RACE:{target}"
        ) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _receipt_relative_path(
    receipt: PairedObservationReceipt,
) -> Path:
    return Path(
        "inputs",
        "paired-observations",
        (
            f"{receipt.sample_cohort.casefold()}-"
            f"{receipt.sample_index:03d}-"
            f"{receipt.topology_id.casefold()}.json"
        ),
    )


def materialize_formal_experiment(
    *,
    runtime_root: Path,
    result: FormalExperimentResult,
    receipts: tuple[PairedObservationReceipt, ...],
    report_markdown: str,
) -> MaterializedFormalExperiment:
    """Persist exactly one immutable formal-E0 result and evidence index."""

    if (
        _RUN_ID.fullmatch(result.offline_run_id) is None
        or result.offline_run_id.casefold() in _MUTABLE_ALIASES
    ):
        raise FormalExperimentStoreError(
            "EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED"
        )
    run_root = Path(runtime_root).resolve() / result.offline_run_id
    _reject_mutable_path(run_root)
    manifest_path = run_root / "manifest.json"
    authority_path = run_root / "bootstrap" / "authority-snapshot.json"
    dataset_path = run_root / "inputs" / "dataset-manifest-ref.json"
    result_path = run_root / "artifacts" / "formal-experiment-result.json"
    topology_path = run_root / "artifacts" / "topology-evaluation.json"
    behavior_path = run_root / "artifacts" / "behavior-metrics.json"
    risk_path = run_root / "artifacts" / "risk-metrics.json"
    profit_path = run_root / "artifacts" / "profit-metrics.json"
    determinism_path = (
        run_root / "artifacts" / "determinism-receipt.json"
    )
    markdown_path = (
        run_root / "reports" / "zh" / "formal-e0-experiment.md"
    )
    index_path = run_root / "artifact-index.json"
    receipt_paths = {
        run_root / _receipt_relative_path(receipt): asdict(receipt)
        for receipt in receipts
    }
    if len(receipt_paths) != len(receipts):
        raise FormalExperimentStoreError(
            "FORMAL_OBSERVATION_PATH_COLLISION"
        )
    ordered_receipts = tuple(
        sorted(
            receipts,
            key=lambda item: (
                _COHORT_ORDER.get(item.sample_cohort, 99),
                item.sample_index,
                item.topology_id,
            ),
        )
    )
    receipt_set_digest = hashlib.sha256(
        canonical_bytes(
            tuple(item.receipt_digest for item in ordered_receipts)
        )
    ).hexdigest()
    expected_receipt_ref = f"receipt-set-digest:{receipt_set_digest}"
    manifest_entries = result.experiment_manifest.get("entry_refs")
    if (
        len(receipts) != result.receipt_count
        or not isinstance(manifest_entries, list)
        or expected_receipt_ref not in manifest_entries
        or result.round2_instance_created
    ):
        raise FormalExperimentStoreError(
            "FORMAL_RESULT_RECEIPT_BINDING_MISMATCH"
        )
    expected_paths = {
        manifest_path,
        authority_path,
        dataset_path,
        result_path,
        topology_path,
        behavior_path,
        risk_path,
        profit_path,
        determinism_path,
        markdown_path,
        index_path,
        *receipt_paths,
    }
    if run_root.exists():
        unexpected = {
            path
            for path in run_root.rglob("*")
            if path.is_file() and path not in expected_paths
        }
        if unexpected:
            raise FormalExperimentStoreError(
                "FORMAL_RUN_CONTAINS_UNEXPECTED_ARTIFACTS"
            )

    write_once_json(manifest_path, result.experiment_manifest)
    write_once_json(authority_path, result.authority_snapshot)
    write_once_json(dataset_path, asdict(result.dataset_manifest_ref))
    for path, value in receipt_paths.items():
        write_once_json(path, value)
    write_once_json(result_path, asdict(result))
    write_once_json(topology_path, asdict(result.topology_evaluation))
    write_once_json(behavior_path, asdict(result.behavior_metrics))
    write_once_json(risk_path, asdict(result.risk_metrics))
    write_once_json(profit_path, asdict(result.profit_metrics))
    determinism = self_digest(
        {
            "receipt_id": f"{result.offline_run_id}:determinism",
            "first_evaluation_summary_digest": (
                result.first_evaluation_summary_digest
            ),
            "second_evaluation_summary_digest": (
                result.second_evaluation_summary_digest
            ),
            "deterministic_repeat_match": (
                result.deterministic_repeat_match
            ),
            "round2_instance_created": False,
            "system_mode": result.system_mode,
            "external_execution_authority": (
                result.external_execution_authority
            ),
            "executable": False,
        },
        "receipt_digest",
    )
    write_once_json(determinism_path, determinism)
    _write_once_text(markdown_path, report_markdown)

    indexed_paths = tuple(
        sorted(
            (
                path
                for path in run_root.rglob("*")
                if path.is_file() and path != index_path
            ),
            key=lambda item: item.relative_to(run_root).as_posix(),
        )
    )
    entries = []
    for path in indexed_paths:
        payload = path.read_bytes()
        entries.append(
            {
                "relative_path": path.relative_to(run_root).as_posix(),
                "byte_length": len(payload),
                "physical_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    artifact_index = self_digest(
        {
            "index_id": f"{result.offline_run_id}:artifact-index",
            "index_version": "1.0.0",
            "entries": entries,
            "formal_experiment_result_digest": result.result_digest,
            "terminal_status": result.terminal_status,
            "round2_precondition_status": (
                result.round2_precondition_status
            ),
            "round2_instance_created": False,
            "system_mode": result.system_mode,
            "external_execution_authority": (
                result.external_execution_authority
            ),
            "executable": False,
        },
        "artifact_index_digest",
    )
    write_once_json(index_path, artifact_index)
    if canonical_bytes(artifact_index) + b"\n" != index_path.read_bytes():
        raise FormalExperimentStoreError(
            "ARTIFACT_INDEX_BYTES_MISMATCH"
        )
    return MaterializedFormalExperiment(
        run_root=run_root,
        manifest_path=manifest_path,
        authority_snapshot_path=authority_path,
        result_path=result_path,
        markdown_path=markdown_path,
        artifact_index_path=index_path,
        artifact_index_digest=str(
            artifact_index["artifact_index_digest"]
        ),
    )


__all__ = [
    "FormalExperimentStoreError",
    "MaterializedFormalExperiment",
    "load_dataset_manifest_ref",
    "load_formal_experiment_contract",
    "load_paired_observation_receipt",
    "load_paired_observation_receipts",
    "materialize_formal_experiment",
]
