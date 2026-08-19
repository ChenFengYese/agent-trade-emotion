#!/usr/bin/env python3.12
"""Prepare, checkpoint, verify, and evaluate a native Codex cluster run.

This utility never calls a model and never dispatches an order.  It gives a
Codex controller a durable handoff around native subagent turns.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from trade_system.theory_paper_v2.application.formal_e0_batch import (  # noqa: E402
    CHALLENGE_CATEGORIES,
    FormalE0BatchRunner,
)
from trade_system.theory_paper_v2.application.generative_topology_run import (  # noqa: E402
    SEMANTIC_MODEL_OUTPUT_SCHEMA,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (  # noqa: E402
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.contracts.validation import (  # noqa: E402
    validate_schema_value,
)
from trade_system.theory_paper_v2.domain.formal_e0_replay import (  # noqa: E402
    replay_action_one_hour,
)


SAMPLE_INDICES = tuple(range(96, 128))
INPUT_TRANSPORT_MODES = {
    "DIRECT_NO_INHERIT_V1",
    "CLEAN_SINGLE_TURN_FORK_V1",
}
OUTPUT_SPECS = {
    "single-proposal": "PROPOSAL",
    "single-self-review": "SELF_REVIEW",
    "single-selection": "SELECTION",
    "cluster-proposal": "PROPOSAL",
    "cluster-challenge": "CHALLENGE_BLIND",
    "cluster-selection": "SELECTION",
}
NON_SELECTOR_KEYS = {
    "single-proposal",
    "single-self-review",
    "cluster-proposal",
    "cluster-challenge",
}


class NativeExperimentStateError(ValueError):
    """A fail-closed native experiment state error."""


class _NoModel:
    """Sentinel proving that context preparation has no model capability."""

    def capability(self) -> None:  # pragma: no cover - must never be called
        raise NativeExperimentStateError("MODEL_CALL_FORBIDDEN_IN_STATE_TOOL")

    def invoke(self, request: object) -> None:  # pragma: no cover
        raise NativeExperimentStateError("MODEL_CALL_FORBIDDEN_IN_STATE_TOOL")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )
    except FileExistsError as exc:
        raise NativeExperimentStateError(
            f"WRITE_ONCE_PATH_EXISTS:{path}"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _replace_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_bytes(value))
    os.replace(temporary, path)


def _load_checkpoint(run_root: Path) -> dict[str, Any]:
    value = load_json_strict(run_root / "checkpoint.json")
    verify_self_digest(value, "checkpoint_digest")
    return value


def _load_manifest(run_root: Path) -> dict[str, Any]:
    value = load_json_strict(run_root / "manifest.json")
    verify_self_digest(value, "manifest_digest")
    return value


def _runner(source_run_root: Path) -> FormalE0BatchRunner:
    return FormalE0BatchRunner(
        prepared_run_root=source_run_root,
        model_port=_NoModel(),
    )


def prepare(
    *,
    source_run_root: Path,
    output_root: Path,
    run_id: str,
    frozen_at: str,
    configured_model: str,
    reasoning_effort: str,
    input_transport_mode: str,
) -> dict[str, Any]:
    if input_transport_mode not in INPUT_TRANSPORT_MODES:
        raise NativeExperimentStateError(
            f"UNSUPPORTED_INPUT_TRANSPORT_MODE:{input_transport_mode}"
        )
    if output_root.exists():
        raise NativeExperimentStateError(
            f"NATIVE_RUN_ROOT_ALREADY_EXISTS:{output_root}"
        )
    output_root.mkdir(parents=True)
    runner = _runner(source_run_root)
    packages = runner._selection_reference_packages()
    context_records: list[dict[str, Any]] = []
    for index in SAMPLE_INDICES:
        package = packages[index][0]
        relative = Path("contexts") / f"{index:03d}.json"
        path = output_root / relative
        payload = canonical_bytes(package.context_document)
        _write_once(path, payload)
        context_records.append(
            {
                "sample_index": index,
                "relative_path": str(relative),
                "context_digest": package.context_document[
                    "context_digest"
                ],
                "physical_sha256": hashlib.sha256(payload).hexdigest(),
                "byte_length": len(payload),
            }
        )
    schema_path = output_root / "semantic-output.schema.json"
    schema_bytes = canonical_bytes(SEMANTIC_MODEL_OUTPUT_SCHEMA)
    _write_once(schema_path, schema_bytes)
    prepared = runner.prepared
    manifest = self_digest(
        {
            "schema_id": "native_codex_cluster_experiment_manifest",
            "schema_version": "1.1.0",
            "run_id": run_id,
            "frozen_at": frozen_at,
            "evidence_class": "PRACTICAL_CODEX_CLUSTER_EXPERIMENT",
            "strict_formal_evidence_eligible": False,
            "strict_formal_exclusion_reasons": [
                "NATIVE_SUBAGENT_PROVIDER_ATTESTATION_NOT_MACHINE_BOUND",
                "NATIVE_SUBAGENT_EXACT_TOKEN_BUDGET_NOT_MACHINE_BOUND",
                *(
                    ["NATIVE_INPUT_FORK_TRANSPORT_NOT_MACHINE_ATTESTED"]
                    if input_transport_mode
                    == "CLEAN_SINGLE_TURN_FORK_V1"
                    else []
                ),
            ],
            "source_formal_run_root": str(source_run_root.resolve()),
            "source_run_bindings_digest": prepared.run_bindings_digest,
            "source_dataset_manifest_digest": (
                prepared.dataset_manifest_digest
            ),
            "source_dataset_payload_digest": (
                prepared.dataset_payload_digest
            ),
            "source_formal_contract_digest": canonical_digest(
                load_json_strict(prepared.formal_contract_path)
            ),
            "sample_indices": list(SAMPLE_INDICES),
            "topology_ids": [
                "SINGLE_STRONG_NATIVE",
                "CLUSTER_BLIND_NATIVE",
            ],
            "native_model_configuration": {
                "configured_model": configured_model,
                "reasoning_effort": reasoning_effort,
                "same_configuration_required_for_every_worker_turn": True,
                "served_model_attestation_status": (
                    "NOT_MACHINE_ATTESTED_NATIVE_COLLABORATION"
                ),
                "exact_token_budget_status": (
                    "NOT_MACHINE_ENFORCED_NATIVE_COLLABORATION"
                ),
            },
            "paired_context_rule": (
                "EXACT_SAME_CANONICAL_CONTEXT_BYTES_PER_SAMPLE"
            ),
            "native_input_transport": {
                "mode": input_transport_mode,
                "controller_turn_contains_exact_context_bytes": True,
                "worker_fork_turns": (
                    1
                    if input_transport_mode
                    == "CLEAN_SINGLE_TURN_FORK_V1"
                    else 0
                ),
                "worker_inherits_older_controller_turns": False,
                "worker_repository_read_forbidden": True,
                "worker_tool_use_forbidden": True,
                "transport_attestation_status": (
                    "PRACTICAL_NOT_MACHINE_ATTESTED"
                ),
            },
            "native_turn_plan": {
                "single_strong": [
                    "PROPOSAL",
                    "SELF_REVIEW",
                    "SELECTION",
                ],
                "cluster_blind": [
                    "PROPOSAL",
                    "CHALLENGE_BLIND",
                    "SELECTION",
                ],
                "calls_per_arm": 3,
                "semantic_schema_identical_each_turn": True,
                "single_agent_identity_persists_for_three_turns": True,
                "cluster_roles_are_separate_fresh_workers": True,
            },
            "scoring_policy": {
                "path_slots": [
                    "PRIMARY",
                    "ALTERNATIVE",
                    "NULL",
                    "OTHER_OR_UNKNOWN",
                ],
                "challenge_categories": list(CHALLENGE_CATEGORIES),
                "selected_action_must_be_exact_feasible_id": True,
                "post_decision_outcome_horizon_hours": 1,
                "outcomes_never_enter_agent_input": True,
                "cluster_preference_requires": (
                    "HIGHER_MEAN_COMPOSITE_WITH_NO_MORE_HARD_ERRORS"
                ),
                "tie_or_unproven_disposition": (
                    "INCONCLUSIVE_USE_SINGLE_AGENT"
                ),
            },
            "context_records": context_records,
            "semantic_output_schema": {
                "relative_path": "semantic-output.schema.json",
                "sha256": hashlib.sha256(schema_bytes).hexdigest(),
            },
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "manifest_digest",
    )
    _write_once(output_root / "manifest.json", canonical_bytes(manifest))
    genesis = canonical_digest(
        {
            "run_id": run_id,
            "manifest_digest": manifest["manifest_digest"],
            "event_kind": "NATIVE_EXPERIMENT_GENESIS",
        }
    )
    checkpoint = self_digest(
        {
            "schema_id": "native_codex_cluster_checkpoint",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "manifest_digest": manifest["manifest_digest"],
            "status": "READY_FOR_NATIVE_CODEX",
            "next_sample_index": SAMPLE_INDICES[0],
            "completed_sample_indices": [],
            "completed_count": 0,
            "last_event_digest": genesis,
            "updated_at": frozen_at,
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "checkpoint_digest",
    )
    _write_once(
        output_root / "checkpoint.json", canonical_bytes(checkpoint)
    )
    return {
        "status": checkpoint["status"],
        "run_root": str(output_root.resolve()),
        "run_id": run_id,
        "manifest_digest": manifest["manifest_digest"],
        "next_sample_index": checkpoint["next_sample_index"],
        "context_count": len(context_records),
    }


def _validate_output(
    *,
    path: Path,
    expected_kind: str,
    feasible_ids: set[str],
    selector: bool,
) -> dict[str, Any]:
    value = load_json_strict(path)
    validate_schema_value(value, SEMANTIC_MODEL_OUTPUT_SCHEMA)
    if value.get("output_kind") != expected_kind:
        raise NativeExperimentStateError(
            f"OUTPUT_KIND_MISMATCH:{path}:{expected_kind}"
        )
    selected = value.get("selected_action")
    if selector:
        if selected not in feasible_ids:
            raise NativeExperimentStateError(
                f"SELECTED_ACTION_NOT_FEASIBLE:{path}:{selected}"
            )
    elif selected is not None:
        raise NativeExperimentStateError(
            f"NON_SELECTOR_SELECTED_ACTION_FORBIDDEN:{path}"
        )
    return value


def record(
    *,
    run_root: Path,
    sample_index: int,
    sources: Mapping[str, Path],
    recorded_at: str,
) -> dict[str, Any]:
    manifest = _load_manifest(run_root)
    checkpoint = _load_checkpoint(run_root)
    if checkpoint["status"] not in {
        "READY_FOR_NATIVE_CODEX",
        "COLLECTING_NATIVE_OUTPUTS",
    }:
        raise NativeExperimentStateError(
            f"CHECKPOINT_NOT_COLLECTIBLE:{checkpoint['status']}"
        )
    if sample_index != checkpoint["next_sample_index"]:
        raise NativeExperimentStateError(
            "SAMPLE_NOT_NEXT:"
            f"{sample_index}:{checkpoint['next_sample_index']}"
        )
    if set(sources) != set(OUTPUT_SPECS):
        raise NativeExperimentStateError("OUTPUT_SOURCE_SET_INCOMPLETE")
    context = load_json_strict(
        run_root / "contexts" / f"{sample_index:03d}.json"
    )
    verify_self_digest(context, "context_digest")
    feasible_ids = {
        str(item["action_id"])
        for item in context["feasible_actions"]
    }
    validated: dict[str, dict[str, Any]] = {}
    for key, expected_kind in OUTPUT_SPECS.items():
        validated[key] = _validate_output(
            path=sources[key],
            expected_kind=expected_kind,
            feasible_ids=feasible_ids,
            selector=key not in NON_SELECTOR_KEYS,
        )
    artifact_records = []
    for key in OUTPUT_SPECS:
        relative = (
            Path("outputs")
            / f"{sample_index:03d}"
            / f"{key}.json"
        )
        payload = canonical_bytes(validated[key])
        _write_once(run_root / relative, payload)
        artifact_records.append(
            {
                "artifact_key": key,
                "relative_path": str(relative),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    event = self_digest(
        {
            "schema_id": "native_codex_cluster_sample_event",
            "schema_version": "1.0.0",
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "sample_index": sample_index,
            "context_digest": context["context_digest"],
            "previous_event_digest": checkpoint["last_event_digest"],
            "artifacts": artifact_records,
            "recorded_at": recorded_at,
            "evidence_class": "PRACTICAL_CODEX_CLUSTER_EXPERIMENT",
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "event_digest",
    )
    _write_once(
        run_root / "events" / f"{sample_index:03d}.json",
        canonical_bytes(event),
    )
    completed = [
        *checkpoint["completed_sample_indices"],
        sample_index,
    ]
    next_index = (
        sample_index + 1 if sample_index < SAMPLE_INDICES[-1] else None
    )
    updated = self_digest(
        {
            **{
                key: value
                for key, value in checkpoint.items()
                if key != "checkpoint_digest"
            },
            "status": (
                "COLLECTING_NATIVE_OUTPUTS"
                if next_index is not None
                else "COLLECTION_COMPLETE_PENDING_EVALUATION"
            ),
            "next_sample_index": next_index,
            "completed_sample_indices": completed,
            "completed_count": len(completed),
            "last_event_digest": event["event_digest"],
            "updated_at": recorded_at,
        },
        "checkpoint_digest",
    )
    _replace_checkpoint(run_root / "checkpoint.json", updated)
    return {
        "status": updated["status"],
        "sample_index": sample_index,
        "completed_count": updated["completed_count"],
        "next_sample_index": updated["next_sample_index"],
        "event_digest": event["event_digest"],
    }


def _path_coverage(outputs: list[Mapping[str, Any]]) -> Decimal:
    slots = (
        any(item.get("primary_path") for item in outputs),
        any(item.get("alternative_paths") for item in outputs),
        any(item.get("null_path") for item in outputs),
        any(item.get("other_or_unknown_path") for item in outputs),
    )
    return Decimal(sum(slots)) / Decimal(4)


def _challenge_coverage(outputs: list[Mapping[str, Any]]) -> Decimal:
    categories = {
        str(claim.get("category"))
        for item in outputs
        for claim in item.get("challenge_claims", [])
        if isinstance(claim, Mapping)
        and claim.get("category") in CHALLENGE_CATEGORIES
    }
    return Decimal(len(categories)) / Decimal(len(CHALLENGE_CATEGORIES))


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def evaluate(*, run_root: Path, evaluated_at: str) -> dict[str, Any]:
    manifest = _load_manifest(run_root)
    checkpoint = _load_checkpoint(run_root)
    if (
        checkpoint["status"]
        != "COLLECTION_COMPLETE_PENDING_EVALUATION"
        or checkpoint["completed_sample_indices"] != list(SAMPLE_INDICES)
    ):
        raise NativeExperimentStateError(
            "NATIVE_COLLECTION_NOT_COMPLETE"
        )
    runner = _runner(Path(manifest["source_formal_run_root"]))
    packages = runner._selection_reference_packages()
    arm_rows: dict[str, list[dict[str, Any]]] = {
        "SINGLE_STRONG_NATIVE": [],
        "CLUSTER_BLIND_NATIVE": [],
    }
    for index in SAMPLE_INDICES:
        package, _control = packages[index]
        definitions = {
            "SINGLE_STRONG_NATIVE": [
                "single-proposal",
                "single-self-review",
                "single-selection",
            ],
            "CLUSTER_BLIND_NATIVE": [
                "cluster-proposal",
                "cluster-challenge",
                "cluster-selection",
            ],
        }
        for topology_id, keys in definitions.items():
            outputs = [
                load_json_strict(
                    run_root
                    / "outputs"
                    / f"{index:03d}"
                    / f"{key}.json"
                )
                for key in keys
            ]
            selected = str(outputs[-1]["selected_action"])
            feasible = {
                str(item["action_id"])
                for item in package.context_document[
                    "feasible_actions"
                ]
            }
            hard_errors = int(selected not in feasible)
            transition = replay_action_one_hour(
                package.state,
                selected_action_id=selected,
                sample_index=index,
                current_bar=package.current_bar,
                next_bar=package.next_bar,
                account=runner.account,
                control_mode="MODEL_SELECTED",
            )
            paths = _path_coverage(outputs)
            challenges = _challenge_coverage(outputs)
            action_feasible = Decimal(
                int(transition.preview.action_exactly_feasible)
            )
            composite = (
                paths + challenges + action_feasible
            ) / Decimal(3)
            arm_rows[topology_id].append(
                {
                    "sample_index": index,
                    "path_coverage": paths,
                    "challenge_coverage": challenges,
                    "action_feasible": bool(action_feasible),
                    "hard_error_count": hard_errors,
                    "selected_action": selected,
                    "composite_score": composite,
                    "one_hour_net_pnl_fraction": (
                        transition.net_pnl_after_cost_fraction
                    ),
                    "one_hour_transaction_cost_fraction": (
                        transition.transaction_cost_fraction
                    ),
                    "one_hour_primary_path_capture": (
                        transition.primary_path_capture
                    ),
                    "post_decision_next_bar_id": (
                        package.next_bar["bar_id"]
                    ),
                }
            )
    summaries: dict[str, Any] = {}
    for topology_id, rows in arm_rows.items():
        summaries[topology_id] = {
            "sample_count": len(rows),
            "mean_path_coverage": _mean(
                [item["path_coverage"] for item in rows]
            ),
            "mean_challenge_coverage": _mean(
                [item["challenge_coverage"] for item in rows]
            ),
            "mean_composite_score": _mean(
                [item["composite_score"] for item in rows]
            ),
            "hard_error_count": sum(
                item["hard_error_count"] for item in rows
            ),
            "action_counts": dict(
                Counter(item["selected_action"] for item in rows)
            ),
            "one_hour_net_pnl_fraction_sum": sum(
                (
                    item["one_hour_net_pnl_fraction"]
                    for item in rows
                ),
                Decimal(0),
            ),
            "one_hour_transaction_cost_fraction_sum": sum(
                (
                    item["one_hour_transaction_cost_fraction"]
                    for item in rows
                ),
                Decimal(0),
            ),
            "one_hour_primary_path_capture_mean": _mean(
                [
                    item["one_hour_primary_path_capture"]
                    for item in rows
                ]
            ),
        }
    single = summaries["SINGLE_STRONG_NATIVE"]
    cluster = summaries["CLUSTER_BLIND_NATIVE"]
    cluster_preferred = (
        cluster["mean_composite_score"]
        > single["mean_composite_score"]
        and cluster["hard_error_count"] <= single["hard_error_count"]
    )
    result = self_digest(
        {
            "schema_id": "native_codex_cluster_experiment_result",
            "schema_version": "1.0.0",
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "evaluated_at": evaluated_at,
            "evidence_class": "PRACTICAL_CODEX_CLUSTER_EXPERIMENT",
            "strict_formal_evidence_eligible": False,
            "sample_count": len(SAMPLE_INDICES),
            "paired_context_integrity": "PASS",
            "arm_summaries": summaries,
            "sample_rows": arm_rows,
            "selection_status": (
                "PRACTICAL_CLUSTER_PREFERRED"
                if cluster_preferred
                else "INCONCLUSIVE_USE_SINGLE_AGENT"
            ),
            "limitations": [
                "NO_MACHINE_ATTESTED_SERVED_MODEL_EQUALITY",
                "NO_MACHINE_ATTESTED_EXACT_TOKEN_BUDGET_EQUALITY",
                "ONE_HOUR_POST_DECISION_REPLAY_IS_DIAGNOSTIC_NOT_PREDICTIVE_PROOF",
                "HISTORICAL_DECISION_TIME_AGENT_INPUT_STATUS_UNKNOWN",
            ],
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "result_digest",
    )
    _write_once(
        run_root / "evaluation" / "native-result.json",
        canonical_bytes(result),
    )
    updated = self_digest(
        {
            **{
                key: value
                for key, value in checkpoint.items()
                if key != "checkpoint_digest"
            },
            "status": "EXPERIMENT_COMPLETE_PRACTICAL",
            "updated_at": evaluated_at,
            "evaluation_result_digest": result["result_digest"],
        },
        "checkpoint_digest",
    )
    _replace_checkpoint(run_root / "checkpoint.json", updated)
    return {
        "status": updated["status"],
        "selection_status": result["selection_status"],
        "sample_count": result["sample_count"],
        "result_digest": result["result_digest"],
    }


def verify(run_root: Path) -> dict[str, Any]:
    manifest = _load_manifest(run_root)
    checkpoint = _load_checkpoint(run_root)
    if checkpoint["manifest_digest"] != manifest["manifest_digest"]:
        raise NativeExperimentStateError("CHECKPOINT_MANIFEST_MISMATCH")
    records = {
        int(item["sample_index"]): item
        for item in manifest["context_records"]
    }
    for index in SAMPLE_INDICES:
        record = records.get(index)
        if record is None:
            raise NativeExperimentStateError(
                f"CONTEXT_RECORD_MISSING:{index}"
            )
        path = run_root / record["relative_path"]
        if not path.is_file() or _sha(path) != record["physical_sha256"]:
            raise NativeExperimentStateError(
                f"CONTEXT_PHYSICAL_DIGEST_MISMATCH:{index}"
            )
        context = load_json_strict(path)
        verify_self_digest(context, "context_digest")
        if context["context_digest"] != record["context_digest"]:
            raise NativeExperimentStateError(
                f"CONTEXT_SEMANTIC_DIGEST_MISMATCH:{index}"
            )
    previous = canonical_digest(
        {
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "event_kind": "NATIVE_EXPERIMENT_GENESIS",
        }
    )
    for index in checkpoint["completed_sample_indices"]:
        event = load_json_strict(
            run_root / "events" / f"{int(index):03d}.json"
        )
        verify_self_digest(event, "event_digest")
        if (
            event["previous_event_digest"] != previous
            or event["sample_index"] != index
        ):
            raise NativeExperimentStateError(
                f"EVENT_CHAIN_BROKEN:{index}"
            )
        for artifact in event["artifacts"]:
            path = run_root / artifact["relative_path"]
            if not path.is_file() or _sha(path) != artifact["sha256"]:
                raise NativeExperimentStateError(
                    f"OUTPUT_DIGEST_MISMATCH:{index}"
                )
        previous = event["event_digest"]
    if previous != checkpoint["last_event_digest"]:
        raise NativeExperimentStateError(
            "CHECKPOINT_EVENT_HEAD_MISMATCH"
        )
    return {
        "status": checkpoint["status"],
        "run_id": manifest["run_id"],
        "manifest_digest": manifest["manifest_digest"],
        "completed_count": checkpoint["completed_count"],
        "next_sample_index": checkpoint["next_sample_index"],
        "event_chain": "PASS",
        "context_integrity": "PASS",
        "evidence_class": manifest["evidence_class"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    item = commands.add_parser("prepare")
    item.add_argument("--source-run-root", type=Path, required=True)
    item.add_argument("--output-root", type=Path, required=True)
    item.add_argument("--run-id", required=True)
    item.add_argument("--frozen-at", required=True)
    item.add_argument("--configured-model", required=True)
    item.add_argument("--reasoning-effort", required=True)
    item.add_argument(
        "--input-transport-mode",
        choices=sorted(INPUT_TRANSPORT_MODES),
        required=True,
    )
    for name in ("status", "verify", "evaluate"):
        item = commands.add_parser(name)
        item.add_argument("--run-root", type=Path, required=True)
        if name == "evaluate":
            item.add_argument("--evaluated-at", default=_now())
    item = commands.add_parser("record")
    item.add_argument("--run-root", type=Path, required=True)
    item.add_argument("--sample-index", type=int, required=True)
    item.add_argument("--recorded-at", default=_now())
    for key in OUTPUT_SPECS:
        item.add_argument(f"--{key}", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "prepare":
            result = prepare(
                source_run_root=arguments.source_run_root,
                output_root=arguments.output_root,
                run_id=arguments.run_id,
                frozen_at=arguments.frozen_at,
                configured_model=arguments.configured_model,
                reasoning_effort=arguments.reasoning_effort,
                input_transport_mode=arguments.input_transport_mode,
            )
        elif arguments.command in {"status", "verify"}:
            result = verify(arguments.run_root)
        elif arguments.command == "evaluate":
            result = evaluate(
                run_root=arguments.run_root,
                evaluated_at=arguments.evaluated_at,
            )
        else:
            result = record(
                run_root=arguments.run_root,
                sample_index=arguments.sample_index,
                sources={
                    key: getattr(arguments, key.replace("-", "_"))
                    for key in OUTPUT_SPECS
                },
                recorded_at=arguments.recorded_at,
            )
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        return 0
    except (NativeExperimentStateError, ValueError, OSError) as exc:
        sys.stdout.buffer.write(
            canonical_bytes(
                {
                    "status": "NO_GO",
                    "error_code": str(exc),
                    "external_execution_authority": "NONE_E0",
                    "executable": False,
                }
            )
            + b"\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
