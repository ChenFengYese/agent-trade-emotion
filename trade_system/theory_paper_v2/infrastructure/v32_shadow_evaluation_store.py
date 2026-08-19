"""Write-once local persistence for deterministic V3.2 shadow outcomes.

The adapter owns no network, clock, Agent, account, order, fill, position, or
PnL capability.  It verifies that every upstream document is already present
at its exact semantic and physical binding, then persists only a Domain-built
shadow outcome evaluation.

An evaluation file is written before its checkpoint binding.  If the process
stops at that boundary, replaying the identical evaluation adopts the exact
orphaned bytes into the compare-and-swap checkpoint.  A different evaluation
for the same schedule always fails closed.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping

from ..application.v32_shadow_evaluation_port import (
    CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID,
    V32ShadowEvaluationPersistenceError,
    V32ShadowEvaluationStorePort,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    atomic_replace_json,
    confirm_existing_bytes,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_outcome_tick import (
    BATCH_COMPLETION_DIGEST_FIELD,
    BATCH_COMPLETION_SCHEMA_ID,
    OUTCOME_RECEIPT_DIGEST_FIELD,
)
from ..domain.v32_shadow_evaluation import (
    SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD,
    SHADOW_OUTCOME_EVALUATION_SCHEMA_ID,
    verify_v32_shadow_outcome_evaluation_v1,
)


SCHEMA_VERSION = "1.0.0"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_EVALUATION_BINDING_FIELDS = frozenset(
    {
        *_BINDING_FIELDS,
        "run_id",
        "decision_id",
        "cycle_index",
        "horizon",
        "schedule_id",
        "schedule_digest",
        "outcome_receipt_digest",
        "outcome_batch_completion_binding",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "revision",
        "status",
        "evaluation_bindings",
        "created_at",
        "updated_at",
        "network_requests_allowed",
        "agent_calls_allowed",
        "caller_supplied_arm_results_allowed",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "probability_claim",
        "expected_value_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        CHECKPOINT_DIGEST_FIELD,
    }
)
_BATCH_COMPLETION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "batch_id",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "completed_at",
        "resolved_schedule_ids",
        "outcome_receipt_digests",
        "network_requests_during_tail",
        "all_due_schedules_terminal",
        "source_scope",
        "external_execution_authority",
        "executable",
        BATCH_COMPLETION_DIGEST_FIELD,
    }
)
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


class V32ShadowEvaluationStoreError(V32ShadowEvaluationPersistenceError):
    """A V3.2 shadow-evaluation persistence invariant failed closed."""


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ShadowEvaluationStoreError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ShadowEvaluationStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V32ShadowEvaluationStoreError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32ShadowEvaluationStoreError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ShadowEvaluationStoreError(code)
    return value


def _cycle(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32ShadowEvaluationStoreError(code)
    return value


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32ShadowEvaluationStoreError(code)
    return text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _physical_sha(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _exact_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32ShadowEvaluationStoreError(code)
    return {
        "relative_ref": _relative_ref(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def build_v32_shadow_evaluation_checkpoint(
    *, run_id: str, created_at: str
) -> dict[str, Any]:
    run = _text(run_id, "V32_SHADOW_STORE_RUN_ID_INVALID")
    created = _time(created_at, "V32_SHADOW_STORE_TIME_INVALID")
    return self_digest(
        {
            "schema_id": CHECKPOINT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "revision": 0,
            "status": "ACTIVE",
            "evaluation_bindings": [],
            "created_at": created,
            "updated_at": created,
            "network_requests_allowed": False,
            "agent_calls_allowed": False,
            "caller_supplied_arm_results_allowed": False,
            "fill_claim": False,
            "position_claim": False,
            "pnl_claim": False,
            "probability_claim": "NONE",
            "expected_value_allowed": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        CHECKPOINT_DIGEST_FIELD,
    )


def _verify_completion_relation(
    *,
    evaluation: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
    outcome_batch_completion: Mapping[str, Any],
) -> None:
    code = "V32_SHADOW_STORE_BATCH_COMPLETION_INVALID"
    schedule_ids = outcome_batch_completion.get("resolved_schedule_ids")
    receipt_digests = outcome_batch_completion.get("outcome_receipt_digests")
    if (
        not isinstance(outcome_batch_completion, Mapping)
        or set(outcome_batch_completion) != _BATCH_COMPLETION_FIELDS
        or outcome_batch_completion.get("schema_id")
        != BATCH_COMPLETION_SCHEMA_ID
        or outcome_batch_completion.get("schema_version") != SCHEMA_VERSION
        or not isinstance(schedule_ids, list)
        or not isinstance(receipt_digests, list)
        or schedule_ids != sorted(set(schedule_ids))
        or len(schedule_ids) != len(receipt_digests)
        or len(receipt_digests) != len(set(receipt_digests))
        or outcome_batch_completion.get("run_id") != evaluation.get("run_id")
        or evaluation.get("outcome_schedule_id") not in schedule_ids
        or outcome_receipt.get(OUTCOME_RECEIPT_DIGEST_FIELD)
        not in receipt_digests
        or outcome_batch_completion.get("batch_intent_digest")
        != outcome_receipt.get("batch_intent_digest")
        or outcome_batch_completion.get("observation_tick_digest")
        != outcome_receipt.get("observation_tick_digest")
        or outcome_batch_completion.get("raw_evidence_digest")
        != outcome_receipt.get("raw_evidence_digest")
        or outcome_batch_completion.get("all_due_schedules_terminal") is not True
        or outcome_batch_completion.get("network_requests_during_tail") != 0
        or outcome_batch_completion.get("source_scope") != SOURCE_SCOPE
        or outcome_batch_completion.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or outcome_batch_completion.get("executable") is not False
        or _moment(outcome_batch_completion.get("completed_at"), code)
        >= _moment(evaluation.get("evaluated_at"), code)
    ):
        raise V32ShadowEvaluationStoreError(code)


class LocalV32ShadowEvaluationStore:
    """Filesystem adapter for deterministic, non-executable shadow outcomes."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root)
        if supplied.exists() and supplied.is_symlink():
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_ROOT_SYMLINK_FORBIDDEN"
            )
        self.run_root = supplied.absolute()
        ensure_directory_tree(self.run_root)
        if self.run_root.is_symlink():
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_ROOT_SYMLINK_FORBIDDEN"
            )
        self._root_resolved = self.run_root.resolve(strict=True)
        self.checkpoint_path = self._safe_path(
            "shadow-evaluation-v32/checkpoint.json", create_parent=True
        )

    def _safe_path(self, relative_ref: str, *, create_parent: bool = False) -> Path:
        relative = _relative_ref(relative_ref, "V32_SHADOW_STORE_PATH_INVALID")
        lexical = PurePosixPath(relative)
        cursor = self.run_root
        for part in lexical.parts[:-1]:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_SYMLINK_FORBIDDEN"
                )
        target = self.run_root.joinpath(*lexical.parts)
        if target.exists() and target.is_symlink():
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_SYMLINK_FORBIDDEN"
            )
        if create_parent:
            ensure_directory_tree(target.parent)
            cursor = self.run_root
            for part in lexical.parts[:-1]:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise V32ShadowEvaluationStoreError(
                        "V32_SHADOW_STORE_SYMLINK_FORBIDDEN"
                    )
        try:
            target.parent.resolve(strict=True).relative_to(self._root_resolved)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_PATH_ESCAPE"
            ) from exc
        return target

    @contextmanager
    def _lock(self):
        path = self._safe_path(
            ".locks/v32-shadow-evaluation-store.lock", create_parent=True
        )
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    @contextmanager
    def evaluation_guard(self, *, run_id: str):
        _text(run_id, "V32_SHADOW_STORE_RUN_ID_INVALID")
        path = self._safe_path(
            ".locks/v32-shadow-evaluation-composition.lock", create_parent=True
        )
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    def initialize_checkpoint(
        self, *, run_id: str, created_at: str
    ) -> Mapping[str, Any]:
        candidate = build_v32_shadow_evaluation_checkpoint(
            run_id=run_id, created_at=created_at
        )
        with self._lock():
            if self.checkpoint_path.exists():
                current = self._load_checkpoint(run_id=run_id)
                if (
                    current.get("run_id") != candidate["run_id"]
                    or current.get("created_at") != candidate["created_at"]
                ):
                    raise V32ShadowEvaluationStoreError(
                        "V32_SHADOW_STORE_INITIALIZATION_CONFLICT"
                    )
                confirm_existing_json(self.checkpoint_path, current)
                return current
            try:
                write_once_json(self.checkpoint_path, candidate)
            except ValueError as exc:
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_INITIALIZATION_FAILED"
                ) from exc
            return candidate

    def _load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        if (
            not self.checkpoint_path.is_file()
            or self.checkpoint_path.is_symlink()
        ):
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_MISSING"
            )
        try:
            checkpoint = load_json_strict(self.checkpoint_path)
        except ValueError as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_INVALID"
            ) from exc
        self._validate_checkpoint(checkpoint, run_id=run_id)
        try:
            confirm_existing_json(self.checkpoint_path, checkpoint)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_INVALID"
            ) from exc
        return checkpoint

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        with self._lock():
            return self._load_checkpoint(run_id=run_id)

    def _validate_checkpoint(
        self, document: Mapping[str, Any], *, run_id: str
    ) -> None:
        try:
            verify_self_digest(document, CHECKPOINT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        bindings = document.get("evaluation_bindings")
        if (
            not isinstance(document, Mapping)
            or set(document) != _CHECKPOINT_FIELDS
            or document.get("schema_id") != CHECKPOINT_SCHEMA_ID
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("run_id") != run_id
            or document.get("status") != "ACTIVE"
            or isinstance(document.get("revision"), bool)
            or not isinstance(document.get("revision"), int)
            or document.get("revision") < 0
            or not isinstance(bindings, list)
            or document.get("network_requests_allowed") is not False
            or document.get("agent_calls_allowed") is not False
            or document.get("caller_supplied_arm_results_allowed") is not False
            or document.get("fill_claim") is not False
            or document.get("position_claim") is not False
            or document.get("pnl_claim") is not False
            or document.get("probability_claim") != "NONE"
            or document.get("expected_value_allowed") is not False
            or document.get("source_scope") != SOURCE_SCOPE
            or document.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or document.get("executable") is not False
        ):
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_INVALID"
            )
        created = _moment(document.get("created_at"), "V32_SHADOW_STORE_TIME_INVALID")
        updated = _moment(document.get("updated_at"), "V32_SHADOW_STORE_TIME_INVALID")
        if updated < created or document["revision"] != len(bindings):
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_CHECKPOINT_SEQUENCE_INVALID"
            )
        seen: set[str] = set()
        for binding in bindings:
            evaluation = self._read_evaluation_binding(binding)
            schedule_id = str(binding["schedule_id"])
            if schedule_id in seen:
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_DUPLICATE_SCHEDULE"
                )
            seen.add(schedule_id)
            if (
                evaluation.get("run_id") != run_id
                or evaluation.get("decision_id") != binding["decision_id"]
                or evaluation.get("cycle_index") != binding["cycle_index"]
                or evaluation.get("horizon") != binding["horizon"]
                or evaluation.get("outcome_schedule_id") != schedule_id
                or evaluation.get("outcome_schedule_digest")
                != binding["schedule_digest"]
                or evaluation.get("outcome_receipt_binding", {}).get(
                    "semantic_digest"
                )
                != binding["outcome_receipt_digest"]
            ):
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_EVALUATION_BINDING_INVALID"
                )

    def _read_exact_file(self, relative_ref: str) -> tuple[bytes, Mapping[str, Any]]:
        path = self._safe_path(relative_ref)
        if not path.is_file() or path.is_symlink():
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_BOUND_DOCUMENT_MISSING"
            )
        try:
            payload = path.read_bytes()
            document = load_json_strict(path)
        except (OSError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_BOUND_DOCUMENT_INVALID"
            ) from exc
        try:
            confirm_existing_bytes(path, payload)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_BOUND_DOCUMENT_INVALID"
            ) from exc
        return payload, document

    def verify_bound_document(
        self, *, document: Mapping[str, Any], binding: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        normalized = _exact_binding(
            binding, "V32_SHADOW_STORE_INPUT_BINDING_INVALID"
        )
        payload, durable = self._read_exact_file(normalized["relative_ref"])
        try:
            semantic = verify_self_digest(durable, normalized["digest_field"])
        except (TypeError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_INPUT_DIGEST_INVALID"
            ) from exc
        if (
            dict(durable) != dict(document)
            or durable.get("schema_id") != normalized["schema_id"]
            or semantic != normalized["semantic_digest"]
            or hashlib.sha256(payload).hexdigest() != normalized["physical_sha256"]
            or normalized["physical_sha256"] != _physical_sha(durable)
        ):
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_INPUT_BINDING_MISMATCH"
            )
        return durable

    @staticmethod
    def _evaluation_ref(evaluation: Mapping[str, Any]) -> str:
        cycle = _cycle(
            evaluation.get("cycle_index"), "V32_SHADOW_STORE_CYCLE_INVALID"
        )
        horizon = _text(
            evaluation.get("horizon"), "V32_SHADOW_STORE_HORIZON_INVALID"
        )
        if horizon not in {"15M", "1H", "4H"}:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_HORIZON_INVALID"
            )
        schedule_id = _digest(
            evaluation.get("outcome_schedule_id"),
            "V32_SHADOW_STORE_SCHEDULE_ID_INVALID",
        )
        return (
            f"shadow-evaluation-v32/cycles/cycle-{cycle:04d}/"
            f"{horizon.lower()}-{schedule_id}.json"
        )

    def _evaluation_binding(
        self,
        *,
        relative_ref: str,
        evaluation: Mapping[str, Any],
        outcome_batch_completion_binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        path = self._safe_path(relative_ref)
        return {
            "relative_ref": relative_ref,
            "schema_id": SHADOW_OUTCOME_EVALUATION_SCHEMA_ID,
            "digest_field": SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD,
            "semantic_digest": evaluation[
                SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD
            ],
            "physical_sha256": _file_sha256(path),
            "run_id": evaluation["run_id"],
            "decision_id": evaluation["decision_id"],
            "cycle_index": evaluation["cycle_index"],
            "horizon": evaluation["horizon"],
            "schedule_id": evaluation["outcome_schedule_id"],
            "schedule_digest": evaluation["outcome_schedule_digest"],
            "outcome_receipt_digest": evaluation["outcome_receipt_binding"][
                "semantic_digest"
            ],
            "outcome_batch_completion_binding": _exact_binding(
                outcome_batch_completion_binding,
                "V32_SHADOW_STORE_BATCH_COMPLETION_BINDING_INVALID",
            ),
        }

    def _read_evaluation_binding(
        self, value: Any
    ) -> Mapping[str, Any]:
        code = "V32_SHADOW_STORE_EVALUATION_BINDING_INVALID"
        if not isinstance(value, Mapping) or set(value) != _EVALUATION_BINDING_FIELDS:
            raise V32ShadowEvaluationStoreError(code)
        relative_ref = _relative_ref(value.get("relative_ref"), code)
        if value.get("schema_id") != SHADOW_OUTCOME_EVALUATION_SCHEMA_ID or value.get(
            "digest_field"
        ) != SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD:
            raise V32ShadowEvaluationStoreError(code)
        _text(value.get("run_id"), code)
        _text(value.get("decision_id"), code)
        _cycle(value.get("cycle_index"), code)
        if value.get("horizon") not in {"15M", "1H", "4H"}:
            raise V32ShadowEvaluationStoreError(code)
        for field in (
            "semantic_digest",
            "physical_sha256",
            "schedule_id",
            "schedule_digest",
            "outcome_receipt_digest",
        ):
            _digest(value.get(field), code)
        completion_binding = _exact_binding(
            value.get("outcome_batch_completion_binding"), code
        )
        if (
            completion_binding["schema_id"] != BATCH_COMPLETION_SCHEMA_ID
            or completion_binding["digest_field"]
            != BATCH_COMPLETION_DIGEST_FIELD
        ):
            raise V32ShadowEvaluationStoreError(code)
        path = self._safe_path(relative_ref)
        if not path.is_file() or path.is_symlink():
            raise V32ShadowEvaluationStoreError(code)
        try:
            evaluation = load_json_strict(path)
            semantic = verify_self_digest(
                evaluation, SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD
            )
        except (OSError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(code) from exc
        if (
            evaluation.get("schema_id") != SHADOW_OUTCOME_EVALUATION_SCHEMA_ID
            or semantic != value["semantic_digest"]
            or _file_sha256(path) != value["physical_sha256"]
        ):
            raise V32ShadowEvaluationStoreError(code)
        receipt_binding = evaluation.get("outcome_receipt_binding")
        if not isinstance(receipt_binding, Mapping):
            raise V32ShadowEvaluationStoreError(code)
        _, receipt = self._read_exact_file(str(receipt_binding.get("relative_ref")))
        self.verify_bound_document(document=receipt, binding=receipt_binding)
        _, completion = self._read_exact_file(completion_binding["relative_ref"])
        self.verify_bound_document(document=completion, binding=completion_binding)
        _verify_completion_relation(
            evaluation=evaluation,
            outcome_receipt=receipt,
            outcome_batch_completion=completion,
        )
        return evaluation

    def _atomic_checkpoint(self, document: Mapping[str, Any]) -> None:
        atomic_replace_json(
            self.checkpoint_path,
            document,
            short_write_error="V32_SHADOW_CHECKPOINT_SHORT_WRITE",
        )

    def _after_evaluation_write(self, binding: Mapping[str, Any]) -> None:
        """Crash-injection seam; production behavior is deliberately empty."""

    def commit_evaluation(
        self,
        *,
        evaluation: Mapping[str, Any],
        shadow_decision_bundle: Mapping[str, Any],
        outcome_schedule_set: Mapping[str, Any],
        outcome_receipt: Mapping[str, Any],
        outcome_batch_completion: Mapping[str, Any],
        outcome_batch_completion_binding: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        try:
            self.verify_bound_document(
                document=shadow_decision_bundle,
                binding=evaluation["shadow_decision_bundle_binding"],
            )
            self.verify_bound_document(
                document=outcome_schedule_set,
                binding=evaluation["outcome_schedule_set_binding"],
            )
            self.verify_bound_document(
                document=outcome_receipt,
                binding=evaluation["outcome_receipt_binding"],
            )
            self.verify_bound_document(
                document=outcome_batch_completion,
                binding=outcome_batch_completion_binding,
            )
            _verify_completion_relation(
                evaluation=evaluation,
                outcome_receipt=outcome_receipt,
                outcome_batch_completion=outcome_batch_completion,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, V32ShadowEvaluationStoreError):
                raise
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_INPUT_BINDING_INVALID"
            ) from exc
        try:
            evaluation_digest = verify_v32_shadow_outcome_evaluation_v1(
                evaluation,
                shadow_decision_bundle=shadow_decision_bundle,
                outcome_schedule_set=outcome_schedule_set,
                outcome_receipt=outcome_receipt,
            )
        except (TypeError, ValueError) as exc:
            raise V32ShadowEvaluationStoreError(
                "V32_SHADOW_STORE_EVALUATION_INVALID"
            ) from exc
        expected = _digest(
            expected_checkpoint_digest, "V32_SHADOW_STORE_CAS_DIGEST_INVALID"
        )
        run_id = _text(
            evaluation.get("run_id"), "V32_SHADOW_STORE_RUN_ID_INVALID"
        )
        relative_ref = self._evaluation_ref(evaluation)
        with self._lock():
            current = self._load_checkpoint(run_id=run_id)
            existing = next(
                (
                    binding
                    for binding in current["evaluation_bindings"]
                    if binding["schedule_id"] == evaluation["outcome_schedule_id"]
                ),
                None,
            )
            if existing is not None:
                durable = self._read_evaluation_binding(existing)
                if dict(durable) != dict(evaluation):
                    raise V32ShadowEvaluationStoreError(
                        "V32_SHADOW_STORE_SCHEDULE_WRITE_ONCE_CONFLICT"
                    )
                confirm_existing_json(self._safe_path(relative_ref), evaluation)
                return {
                    "status": "IDEMPOTENT_REPLAY",
                    "evaluation_binding": dict(existing),
                    "checkpoint": current,
                }
            if current[CHECKPOINT_DIGEST_FIELD] != expected:
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_CAS_CONFLICT"
                )
            path = self._safe_path(relative_ref, create_parent=True)
            try:
                write_once_json(path, evaluation)
            except ValueError as exc:
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_SCHEDULE_WRITE_ONCE_CONFLICT"
                ) from exc
            binding = self._evaluation_binding(
                relative_ref=relative_ref,
                evaluation=evaluation,
                outcome_batch_completion_binding=outcome_batch_completion_binding,
            )
            if binding["semantic_digest"] != evaluation_digest:
                raise V32ShadowEvaluationStoreError(
                    "V32_SHADOW_STORE_EVALUATION_DIGEST_INVALID"
                )
            self._after_evaluation_write(binding)
            candidate = dict(current)
            candidate.pop(CHECKPOINT_DIGEST_FIELD, None)
            candidate.update(
                {
                    "revision": int(current["revision"]) + 1,
                    "evaluation_bindings": [
                        *current["evaluation_bindings"],
                        binding,
                    ],
                    "updated_at": evaluation["evaluated_at"],
                }
            )
            next_checkpoint = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
            self._validate_checkpoint(next_checkpoint, run_id=run_id)
            self._atomic_checkpoint(next_checkpoint)
            return {
                "status": "COMMITTED",
                "evaluation_binding": binding,
                "checkpoint": next_checkpoint,
            }


__all__ = [
    "CHECKPOINT_DIGEST_FIELD",
    "CHECKPOINT_SCHEMA_ID",
    "LocalV32ShadowEvaluationStore",
    "V32ShadowEvaluationStoreError",
    "V32ShadowEvaluationStorePort",
    "build_v32_shadow_evaluation_checkpoint",
]
