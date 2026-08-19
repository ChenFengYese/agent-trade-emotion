"""Write-once artifacts and a CAS cursor for the V3.1 outcome monitor.

This store is deliberately separate from the research-cycle checkpoint: a
completed accepted state remains immutable while its one-hour outcome can be
observed later.  Both stores share the same run root and therefore the monitor
can physically verify the accepted-state artifact it is bound to.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.v31_experiment_contracts import (
    MONITOR_SCHEMA_ID,
    OUTCOME_SCHEMA_ID,
)
from ..domain.v31_monitor_runtime import (
    MONITOR_ATTEMPT_SCHEMA_ID,
    MONITOR_CHECKPOINT_SCHEMA_ID,
    MONITOR_CHECKPOINT_SCHEMA_VERSION,
    MONITOR_FAILURE_SCHEMA_ID,
    PUBLIC_SOURCE_RECORD_SCHEMA_ID,
    PUBLIC_SOURCE_SCOPE,
    monitor_cycle_root,
    outcome_observation_from_source_record,
    verify_monitor_resolution_attempt,
    verify_public_outcome_source_record,
)
from .v31_research_store import LocalV31ResearchStore, V31ResearchStoreError


class V31MonitorStoreError(ValueError):
    """The durable monitor chronology or cursor failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"cycle_index", "relative_ref", "semantic_digest", "physical_sha256"}
)
_PLAN_BINDING_FIELDS = frozenset((*_BINDING_FIELDS, "accepted_state_digest"))
_OUTCOME_BINDING_FIELDS = frozenset(
    {
        "cycle_index",
        "raw_capture_ref",
        "raw_capture_sha256",
        "source_record_ref",
        "source_record_digest",
        "source_record_physical_sha256",
        "observation_ref",
        "observation_digest",
        "observation_physical_sha256",
        "outcome_receipt_ref",
        "outcome_receipt_digest",
        "outcome_receipt_physical_sha256",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "revision",
        "status",
        "total_cycles",
        "plan_bindings",
        "resolution_attempt_bindings",
        "outcome_bindings",
        "last_outcome_receipt_digest",
        "failure_ref",
        "failure_digest",
        "resume_allowed",
        "created_at",
        "updated_at",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "credential_use",
        "funds_access",
        "checkpoint_digest",
    }
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31MonitorStoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31MonitorStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V31MonitorStoreError(code)
    return parsed.astimezone(UTC)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31MonitorStoreError(code)
    return value


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(document)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LocalV31MonitorStore:
    """One local, write-once, no-retry outcome-monitor store."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self._artifacts = LocalV31ResearchStore(self.run_root)
        self.checkpoint_path = self.run_root / "monitor" / "checkpoint.json"

    @contextmanager
    def _lock(self):
        path = self.run_root / ".locks" / "v31-monitor-checkpoint.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def write_raw(self, *, relative_ref: str, payload: bytes) -> Mapping[str, str]:
        return self._artifacts.write_raw(relative_ref=relative_ref, payload=payload)

    def read_raw(
        self, *, relative_ref: str, expected_sha256: str | None = None
    ) -> bytes:
        return self._artifacts.read_raw(
            relative_ref=relative_ref, expected_sha256=expected_sha256
        )

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]:
        return self._artifacts.write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        return self._artifacts.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        return self._artifacts.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        experiment_contract_digest: str,
        total_cycles: int,
        created_at: str,
    ) -> Mapping[str, Any]:
        if self.checkpoint_path.exists():
            current = self.load_checkpoint(run_id=run_id)
            if (
                current["experiment_contract_digest"] != experiment_contract_digest
                or current["total_cycles"] != total_cycles
            ):
                raise V31MonitorStoreError("V31_MONITOR_INITIALIZATION_CONFLICT")
            return current
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or isinstance(total_cycles, bool)
            or not isinstance(total_cycles, int)
            or total_cycles != 8
        ):
            raise V31MonitorStoreError("V31_MONITOR_INITIALIZATION_INVALID")
        _digest(
            experiment_contract_digest,
            "V31_MONITOR_EXPERIMENT_CONTRACT_DIGEST_INVALID",
        )
        _time(created_at, "V31_MONITOR_CHECKPOINT_TIME_INVALID")
        checkpoint = self_digest(
            {
                "schema_id": MONITOR_CHECKPOINT_SCHEMA_ID,
                "schema_version": MONITOR_CHECKPOINT_SCHEMA_VERSION,
                "run_id": run_id,
                "experiment_contract_digest": experiment_contract_digest,
                "revision": 0,
                "status": "ACTIVE",
                "total_cycles": total_cycles,
                "plan_bindings": [],
                "resolution_attempt_bindings": [],
                "outcome_bindings": [],
                "last_outcome_receipt_digest": None,
                "failure_ref": None,
                "failure_digest": None,
                "resume_allowed": True,
                "created_at": created_at,
                "updated_at": created_at,
                "chat_history_is_authority": False,
                "source_scope": PUBLIC_SOURCE_SCOPE,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
                "account_access": False,
                "order_submission": False,
                "credential_use": False,
                "funds_access": False,
            },
            "checkpoint_digest",
        )
        self._validate_checkpoint(checkpoint, run_id=run_id)
        write_once_json(self.checkpoint_path, checkpoint)
        return checkpoint

    def _verify_json_binding(
        self,
        binding: Mapping[str, Any],
        *,
        expected_fields: frozenset[str],
        expected_ref: str,
        digest_field: str,
        schema_id: str | None,
    ) -> Mapping[str, Any]:
        if (
            not isinstance(binding, Mapping)
            or set(binding) != expected_fields
            or binding.get("relative_ref") != expected_ref
        ):
            raise V31MonitorStoreError("V31_MONITOR_ARTIFACT_BINDING_INVALID")
        semantic = _digest(
            binding.get("semantic_digest"), "V31_MONITOR_ARTIFACT_BINDING_INVALID"
        )
        physical = _digest(
            binding.get("physical_sha256"), "V31_MONITOR_ARTIFACT_BINDING_INVALID"
        )
        document = self.read_document(
            relative_ref=expected_ref,
            digest_field=digest_field,
            expected_semantic_digest=semantic,
        )
        path = self._artifacts._safe_path(expected_ref)
        if (
            hashlib.sha256(path.read_bytes()).hexdigest() != physical
            or (schema_id is not None and document.get("schema_id") != schema_id)
        ):
            raise V31MonitorStoreError("V31_MONITOR_ARTIFACT_BINDING_INVALID")
        return document

    def _validate_checkpoint(
        self, checkpoint: Mapping[str, Any], *, run_id: str
    ) -> None:
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_DIGEST_INVALID") from exc
        if (
            set(checkpoint) != _CHECKPOINT_FIELDS
            or checkpoint.get("schema_id") != MONITOR_CHECKPOINT_SCHEMA_ID
            or checkpoint.get("schema_version") != MONITOR_CHECKPOINT_SCHEMA_VERSION
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("status") not in {"ACTIVE", "TERMINAL", "FAILED_CLOSED"}
            or checkpoint.get("total_cycles") != 8
            or checkpoint.get("chat_history_is_authority") is not False
            or checkpoint.get("source_scope") != PUBLIC_SOURCE_SCOPE
            or checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or any(
                checkpoint.get(name) is not False
                for name in (
                    "executable",
                    "account_access",
                    "order_submission",
                    "credential_use",
                    "funds_access",
                )
            )
        ):
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_INVALID")
        _digest(
            checkpoint.get("experiment_contract_digest"),
            "V31_MONITOR_EXPERIMENT_CONTRACT_DIGEST_INVALID",
        )
        revision = checkpoint.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_REVISION_INVALID")
        created = _time(
            checkpoint.get("created_at"), "V31_MONITOR_CHECKPOINT_TIME_INVALID"
        )
        updated = _time(
            checkpoint.get("updated_at"), "V31_MONITOR_CHECKPOINT_TIME_INVALID"
        )
        if updated < created:
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_TIME_INVALID")
        plans = checkpoint.get("plan_bindings")
        attempts = checkpoint.get("resolution_attempt_bindings")
        outcomes = checkpoint.get("outcome_bindings")
        if (
            not isinstance(plans, list)
            or not isinstance(attempts, list)
            or not isinstance(outcomes, list)
            or not 0 <= len(outcomes) <= len(attempts) <= len(plans) <= 8
            or len(attempts) - len(outcomes) > 1
        ):
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_COUNTS_INVALID")

        plan_documents: list[Mapping[str, Any]] = []
        for cycle_index, binding in enumerate(plans, start=1):
            if binding.get("cycle_index") != cycle_index:
                raise V31MonitorStoreError("V31_MONITOR_PLAN_SEQUENCE_INVALID")
            root = monitor_cycle_root(cycle_index)
            plan = self._verify_json_binding(
                binding,
                expected_fields=_PLAN_BINDING_FIELDS,
                expected_ref=f"{root}/monitor-plan.json",
                digest_field="monitor_plan_digest",
                schema_id=MONITOR_SCHEMA_ID,
            )
            if (
                plan.get("run_id") != run_id
                or plan.get("cycle_index") != cycle_index
                or plan.get("experiment_contract_digest")
                != checkpoint["experiment_contract_digest"]
                or plan.get("origin_bindings", {})
                .get("accepted_state", {})
                .get("digest")
                != binding.get("accepted_state_digest")
            ):
                raise V31MonitorStoreError("V31_MONITOR_PLAN_BINDING_INVALID")
            plan_documents.append(plan)

        attempt_documents: list[Mapping[str, Any]] = []
        for cycle_index, binding in enumerate(attempts, start=1):
            if binding.get("cycle_index") != cycle_index:
                raise V31MonitorStoreError("V31_MONITOR_ATTEMPT_SEQUENCE_INVALID")
            attempt = self._verify_json_binding(
                binding,
                expected_fields=_BINDING_FIELDS,
                expected_ref=(
                    f"{monitor_cycle_root(cycle_index)}/resolution-attempt.json"
                ),
                digest_field="monitor_attempt_digest",
                schema_id=MONITOR_ATTEMPT_SCHEMA_ID,
            )
            try:
                verify_monitor_resolution_attempt(attempt)
            except ValueError as exc:
                raise V31MonitorStoreError("V31_MONITOR_ATTEMPT_INVALID") from exc
            expected_previous = (
                None
                if cycle_index == 1
                else outcomes[cycle_index - 2]["outcome_receipt_digest"]
            )
            if (
                attempt.get("run_id") != run_id
                or attempt.get("cycle_index") != cycle_index
                or attempt.get("monitor_plan_digest")
                != plan_documents[cycle_index - 1]["monitor_plan_digest"]
                or attempt.get("previous_outcome_receipt_digest")
                != expected_previous
            ):
                raise V31MonitorStoreError("V31_MONITOR_ATTEMPT_BINDING_INVALID")
            attempt_documents.append(attempt)

        for cycle_index, binding in enumerate(outcomes, start=1):
            if (
                not isinstance(binding, Mapping)
                or set(binding) != _OUTCOME_BINDING_FIELDS
                or binding.get("cycle_index") != cycle_index
            ):
                raise V31MonitorStoreError("V31_MONITOR_OUTCOME_BINDING_INVALID")
            root = monitor_cycle_root(cycle_index)
            raw_ref = f"{root}/outcome-raw.bin"
            raw_sha = _digest(
                binding.get("raw_capture_sha256"),
                "V31_MONITOR_OUTCOME_BINDING_INVALID",
            )
            if binding.get("raw_capture_ref") != raw_ref:
                raise V31MonitorStoreError("V31_MONITOR_OUTCOME_BINDING_INVALID")
            try:
                self.read_raw(relative_ref=raw_ref, expected_sha256=raw_sha)
            except V31ResearchStoreError as exc:
                raise V31MonitorStoreError(
                    "V31_MONITOR_RAW_DIGEST_MISMATCH"
                ) from exc

            def projection(prefix: str, ref: str) -> dict[str, Any]:
                return {
                    "cycle_index": cycle_index,
                    "relative_ref": binding[f"{prefix}_ref"],
                    "semantic_digest": binding[f"{prefix}_digest"],
                    "physical_sha256": binding[f"{prefix}_physical_sha256"],
                }

            source = self._verify_json_binding(
                projection("source_record", f"{root}/source-record.json"),
                expected_fields=_BINDING_FIELDS,
                expected_ref=f"{root}/source-record.json",
                digest_field="source_record_digest",
                schema_id=PUBLIC_SOURCE_RECORD_SCHEMA_ID,
            )
            observation = self._verify_json_binding(
                projection("observation", f"{root}/outcome-observation.json"),
                expected_fields=_BINDING_FIELDS,
                expected_ref=f"{root}/outcome-observation.json",
                digest_field="observation_digest",
                schema_id=None,
            )
            receipt = self._verify_json_binding(
                projection("outcome_receipt", f"{root}/outcome-receipt.json"),
                expected_fields=_BINDING_FIELDS,
                expected_ref=f"{root}/outcome-receipt.json",
                digest_field="outcome_receipt_digest",
                schema_id=OUTCOME_SCHEMA_ID,
            )
            try:
                verify_public_outcome_source_record(source)
                rebuilt_observation = outcome_observation_from_source_record(
                    source
                ).to_document()
            except ValueError as exc:
                raise V31MonitorStoreError("V31_MONITOR_SOURCE_RECORD_INVALID") from exc
            expected_previous = (
                None
                if cycle_index == 1
                else outcomes[cycle_index - 2]["outcome_receipt_digest"]
            )
            if (
                source.get("raw_capture_ref") != raw_ref
                or source.get("raw_capture_sha256") != raw_sha
                or source.get("monitor_plan_digest")
                != plan_documents[cycle_index - 1]["monitor_plan_digest"]
                or observation != rebuilt_observation
                or receipt.get("run_id") != run_id
                or receipt.get("cycle_index") != cycle_index
                or receipt.get("monitor_plan_digest")
                != plan_documents[cycle_index - 1]["monitor_plan_digest"]
                or receipt.get("observation") != observation
                or receipt.get("previous_outcome_receipt_digest")
                != expected_previous
            ):
                raise V31MonitorStoreError("V31_MONITOR_OUTCOME_BINDING_INVALID")

        last_digest = checkpoint.get("last_outcome_receipt_digest")
        if (not outcomes and last_digest is not None) or (
            outcomes and last_digest != outcomes[-1]["outcome_receipt_digest"]
        ):
            raise V31MonitorStoreError("V31_MONITOR_OUTCOME_HEAD_INVALID")
        status = checkpoint["status"]
        if status == "TERMINAL" and len(outcomes) != 8:
            raise V31MonitorStoreError("V31_MONITOR_TERMINAL_INVALID")
        if status == "ACTIVE" and len(outcomes) == 8:
            raise V31MonitorStoreError("V31_MONITOR_ACTIVE_INVALID")
        failure_ref = checkpoint.get("failure_ref")
        failure_digest = checkpoint.get("failure_digest")
        if status == "FAILED_CLOSED":
            if (
                not isinstance(failure_ref, str)
                or not failure_ref
                or _HEX_64.fullmatch(str(failure_digest or "")) is None
                or checkpoint.get("resume_allowed") is not False
            ):
                raise V31MonitorStoreError("V31_MONITOR_FAILURE_BINDING_INVALID")
            failure = self.read_document(
                relative_ref=failure_ref,
                digest_field="failure_digest",
                expected_semantic_digest=failure_digest,
            )
            if (
                failure.get("schema_id") != MONITOR_FAILURE_SCHEMA_ID
                or failure.get("run_id") != run_id
                or failure.get("resume_allowed") is not False
                or failure.get("external_execution_authority")
                != "NONE_LOCAL_SIMULATION"
                or failure.get("executable") is not False
            ):
                raise V31MonitorStoreError("V31_MONITOR_FAILURE_BINDING_INVALID")
        elif (
            failure_ref is not None
            or failure_digest is not None
            or checkpoint.get("resume_allowed") is not True
        ):
            raise V31MonitorStoreError("V31_MONITOR_FAILURE_BINDING_INVALID")

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        try:
            checkpoint = load_json_strict(self.checkpoint_path)
        except (FileNotFoundError, ValueError) as exc:
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_MISSING") from exc
        self._validate_checkpoint(checkpoint, run_id=run_id)
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        with self._lock():
            current = self.load_checkpoint(run_id=run_id)
            if current["checkpoint_digest"] != expected_checkpoint_digest:
                raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_CAS_FAILED")
            if current["status"] != "ACTIVE":
                raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_CLOSED")
            candidate = self_digest(dict(checkpoint), "checkpoint_digest")
            self._validate_checkpoint(candidate, run_id=run_id)
            if (
                candidate["revision"] != current["revision"] + 1
                or candidate["experiment_contract_digest"]
                != current["experiment_contract_digest"]
                or candidate["total_cycles"] != current["total_cycles"]
                or candidate["created_at"] != current["created_at"]
                or _time(
                    candidate["updated_at"], "V31_MONITOR_CHECKPOINT_TIME_INVALID"
                )
                < _time(
                    current["updated_at"], "V31_MONITOR_CHECKPOINT_TIME_INVALID"
                )
            ):
                raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_TRANSITION_INVALID")
            deltas = (
                len(candidate["plan_bindings"]) - len(current["plan_bindings"]),
                len(candidate["resolution_attempt_bindings"])
                - len(current["resolution_attempt_bindings"]),
                len(candidate["outcome_bindings"])
                - len(current["outcome_bindings"]),
                1 if candidate["status"] == "FAILED_CLOSED" else 0,
            )
            if deltas not in {
                (1, 0, 0, 0),
                (0, 1, 0, 0),
                (0, 0, 1, 0),
                (0, 0, 0, 1),
            }:
                raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_TRANSITION_INVALID")
            for position, field in enumerate(
                (
                    "plan_bindings",
                    "resolution_attempt_bindings",
                    "outcome_bindings",
                )
            ):
                delta = deltas[position]
                prefix = candidate[field] if delta == 0 else candidate[field][:-1]
                if prefix != current[field]:
                    raise V31MonitorStoreError(
                        "V31_MONITOR_CHECKPOINT_HISTORY_MUTATION_FORBIDDEN"
                    )
            if deltas == (1, 0, 0, 0) or deltas == (0, 1, 0, 0):
                if (
                    candidate["status"] != "ACTIVE"
                    or candidate["last_outcome_receipt_digest"]
                    != current["last_outcome_receipt_digest"]
                    or candidate["failure_ref"] != current["failure_ref"]
                    or candidate["failure_digest"] != current["failure_digest"]
                ):
                    raise V31MonitorStoreError(
                        "V31_MONITOR_CHECKPOINT_TRANSITION_INVALID"
                    )
            elif deltas == (0, 0, 1, 0):
                expected_status = (
                    "TERMINAL"
                    if len(candidate["outcome_bindings"])
                    == candidate["total_cycles"]
                    else "ACTIVE"
                )
                if (
                    candidate["status"] != expected_status
                    or candidate["failure_ref"] != current["failure_ref"]
                    or candidate["failure_digest"] != current["failure_digest"]
                ):
                    raise V31MonitorStoreError(
                        "V31_MONITOR_CHECKPOINT_TRANSITION_INVALID"
                    )
            else:
                failure = self.read_document(
                    relative_ref=str(candidate["failure_ref"]),
                    digest_field="failure_digest",
                    expected_semantic_digest=str(candidate["failure_digest"]),
                )
                if (
                    candidate["status"] != "FAILED_CLOSED"
                    or failure.get("checkpoint_digest_before_failure")
                    != current["checkpoint_digest"]
                ):
                    raise V31MonitorStoreError(
                        "V31_MONITOR_CHECKPOINT_TRANSITION_INVALID"
                    )
            _atomic_json(self.checkpoint_path, candidate)
            return candidate

    def fail_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        failure_code: str,
        failure_summary: str,
        occurred_at: str,
    ) -> Mapping[str, Any]:
        checkpoint = self.load_checkpoint(run_id=run_id)
        if checkpoint["checkpoint_digest"] != expected_checkpoint_digest:
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_CAS_FAILED")
        if checkpoint["status"] != "ACTIVE":
            raise V31MonitorStoreError("V31_MONITOR_CHECKPOINT_CLOSED")
        _time(occurred_at, "V31_MONITOR_FAILURE_TIME_INVALID")
        if not isinstance(failure_code, str) or not failure_code.strip():
            raise V31MonitorStoreError("V31_MONITOR_FAILURE_CODE_INVALID")
        if not isinstance(failure_summary, str) or not failure_summary.strip():
            raise V31MonitorStoreError("V31_MONITOR_FAILURE_SUMMARY_INVALID")
        failure = self_digest(
            {
                "schema_id": MONITOR_FAILURE_SCHEMA_ID,
                "schema_version": "1.0.0",
                "run_id": run_id,
                "occurred_at": occurred_at,
                "failure_code": failure_code.strip(),
                "failure_summary": failure_summary.strip(),
                "checkpoint_digest_before_failure": checkpoint[
                    "checkpoint_digest"
                ],
                "planned_cycles": len(checkpoint["plan_bindings"]),
                "reserved_attempts": len(
                    checkpoint["resolution_attempt_bindings"]
                ),
                "resolved_cycles": len(checkpoint["outcome_bindings"]),
                "resume_allowed": False,
                "source_scope": PUBLIC_SOURCE_SCOPE,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "failure_digest",
        )
        relative_ref = (
            f"monitor/failures/revision-{int(checkpoint['revision']):04d}.json"
        )
        binding = self.write_document(
            relative_ref=relative_ref,
            document=failure,
            digest_field="failure_digest",
        )
        return self.replace_checkpoint(
            run_id=run_id,
            expected_checkpoint_digest=expected_checkpoint_digest,
            checkpoint={
                **checkpoint,
                "revision": int(checkpoint["revision"]) + 1,
                "status": "FAILED_CLOSED",
                "failure_ref": binding["relative_ref"],
                "failure_digest": binding["semantic_digest"],
                "resume_allowed": False,
                "updated_at": occurred_at,
            },
        )


__all__ = [
    "LocalV31MonitorStore",
    "V31MonitorStoreError",
    "monitor_cycle_root",
]
