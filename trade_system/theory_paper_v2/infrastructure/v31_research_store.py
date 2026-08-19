"""Durable local store for the single V3.1 research chronology.

The store owns filesystem mechanics only: write-once artifacts, a physically
verified append-only event chain, and a compare-and-swap checkpoint.  It does
not infer market state, select actions, or grant experiment/execution authority.
"""

from __future__ import annotations

import hashlib
import fcntl
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.agent_research_contract import (
    AgentResearchContractError,
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)


class V31ResearchStoreError(ValueError):
    """A V3.1 artifact, event, or checkpoint violated durable-state rules."""


ZERO_DIGEST = "0" * 64
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
_SEMANTIC_ADMISSION_KEYS = frozenset((*_EVENT_ORDER, "ASSEMBLY_BUNDLE"))
_ASSEMBLY_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "assembly_parameter_names",
        "assembly_signature_digest",
        "typed_assembly_inputs",
        "typed_assembly_inputs_digest",
        "selection_plan",
        "completed_at",
        "recorded_at_by_event",
        "expected_artifact_digests",
        "source_boundary",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        "assembly_bundle_digest",
    }
)
_EVENT_CONTRACT = {
    "INPUTS_ADMITTED": (
        "theory_paper_v2_v31_inputs_receipt",
        "inputs_receipt_digest",
        "NONE_LOCAL_SIMULATION",
    ),
    "PROPOSAL_SEALED": (
        "theory_paper_v2_v31_agent_proposal",
        "agent_proposal_digest",
        "NONE_LOCAL_SIMULATION",
    ),
    "EVALUATION_SEALED": (
        "theory_paper_v2_v31_cycle_preselection",
        "preselection_digest",
        "NONE_LOCAL_SIMULATION",
    ),
    "SELECTION_SEALED": (
        "theory_paper_v2_v31_action_selection",
        "action_selection_digest",
        "NONE_LOCAL_SIMULATION",
    ),
    "STATE_ACCEPTED": (
        "theory_paper_v2_v31_accepted_research_state",
        "accepted_state_digest",
        "NONE_LOCAL_SIMULATION",
    ),
    "COMPLETION_SEALED": (
        "theory_paper_v2_v31_completion_receipt",
        "completion_receipt_digest",
        "NONE_LOCAL_SIMULATION",
    ),
}
_PRESELECTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "inputs_receipt_digest",
        "agent_proposal_digest",
        "information_event_digests",
        "information_revision_registry_digest",
        "association_estimation_receipt_digests",
        "pit_dataset_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "prior_graph_digest",
        "graph_delta_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "probability_cloud_transition",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "path_evaluation",
        "action_evaluation_digest",
        "candidate_path_admissibility_digest",
        "candidate_path_admissibility",
        "selectable_candidate_ids",
        "artifact_bindings_digest",
        "binding_order",
        "graph_chain_policy",
        "selection_fields_admitted",
        "external_execution_authority",
        "executable",
        "preselection_digest",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "action_evaluation_digest",
        "selected_candidate_id",
        "selected_action",
        "reason",
        "alternative_explanations",
        "failure_conditions",
        "next_review_at",
        "selected_at",
        "external_execution_authority",
        "executable",
        "action_selection_digest",
    }
)
_ACCEPTED_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "selected_at",
        "symbol",
        "inputs_receipt_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_evaluation_digest",
        "action_selection_digest",
        "agent_proposal_digest",
        "selected_candidate_id",
        "selected_candidate_evaluation_digest",
        "status",
        "selection_boundary",
        "external_execution_authority",
        "executable",
        "accepted_state_digest",
    }
)
_COMPLETION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "selected_at",
        "completed_at",
        "inputs_receipt_digest",
        "accepted_state_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_selection_digest",
        "selected_candidate_id",
        "completion_status",
        "external_execution_authority",
        "executable",
        "completion_receipt_digest",
    }
)
_DOCUMENT_FIELDS = {
    "EVALUATION_SEALED": _PRESELECTION_FIELDS,
    "SELECTION_SEALED": _SELECTION_FIELDS,
    "STATE_ACCEPTED": _ACCEPTED_FIELDS,
    "COMPLETION_SEALED": _COMPLETION_FIELDS,
}
_PRESELECTION_BINDING_FIELDS = (
    "inputs_receipt_digest",
    "agent_proposal_digest",
    "information_event_digests",
    "information_revision_registry_digest",
    "association_estimation_receipt_digests",
    "pit_dataset_digest",
    "datum_revision_registry_digest",
    "sentiment_state_digest",
    "sentiment_change_digest",
    "prior_graph_digest",
    "graph_delta_digest",
    "graph_state_digest",
    "hypothesis_registry_digest",
    "expectation_ledger_digest",
    "dynamic_research_binding_digest",
    "probability_cloud_digest",
    "probability_cloud_transition_digest",
    "scenario_path_set_digest",
    "path_evaluation_digest",
    "action_evaluation_digest",
    "candidate_path_admissibility_digest",
)
_BINDING_ORDER = (
    "INFORMATION_ADMISSION",
    "CUMULATIVE_INFORMATION_REVISION_REGISTRY",
    "PIT_MARKET_DATASET",
    "CUMULATIVE_DATUM_REVISION_REGISTRY",
    "MULTIDIMENSIONAL_ORDINAL_SENTIMENT_STATE",
    "ORDINAL_SENTIMENT_CHANGE",
    "TRUSTED_ASSOCIATION_ESTIMATION",
    "APPEND_ONLY_GRAPH_DELTA",
    "OPEN_HYPOTHESIS_REGISTRY",
    "APPEND_ONLY_EXPECTATION_LEDGER",
    "PROBABILITY_CLOUD",
    "PROBABILITY_CLOUD_TRANSITION",
    "STRICT_SCENARIO_PATH_SET",
    "THREE_VALUED_PATH_EVALUATION",
    "COMPLETE_ACTION_EVALUATION",
    "PATH_ACTION_ADMISSIBILITY",
    "INDEPENDENT_SELECTION",
)
_ARTIFACT_TIME_FIELD = {
    "INPUTS_ADMITTED": "decision_at",
    "PROPOSAL_SEALED": "decision_at",
    "EVALUATION_SEALED": "decision_at",
    "SELECTION_SEALED": "selected_at",
    "STATE_ACCEPTED": "selected_at",
    "COMPLETION_SEALED": "completed_at",
}
_CHECKPOINT_STATUSES = frozenset(
    {"READY_FOR_CYCLE", "CYCLE_IN_PROGRESS", "FAILED_CLOSED", "TERMINAL"}
)
_GENESIS_BINDING_PAIRS = (
    ("theory_approval_ref", "theory_approval_digest"),
    ("experiment_manifest_ref", "experiment_manifest_digest"),
    ("experiment_authorization_ref", "experiment_authorization_digest"),
    ("current_authority_ref", "current_authority_digest"),
    ("run_genesis_ref", "run_genesis_digest"),
)
_GENESIS_BINDING_FIELDS = frozenset(
    field for pair in _GENESIS_BINDING_PAIRS for field in pair
)
_TRANSPORT_EVIDENCE_BINDING_FIELDS = frozenset(
    {"cycle_index", "relative_ref", "semantic_digest", "physical_sha256"}
)
_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "occurred_at",
        "failure_code",
        "failure_summary",
        "checkpoint_digest_before_failure",
        "event_prefix_length",
        "last_event_digest",
        "resume_allowed",
        "external_execution_authority",
        "executable",
        "failure_digest",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "revision",
        "status",
        "total_cycles",
        "completed_cycles",
        "next_cycle_index",
        "active_cycle_index",
        "accepted_state_ref",
        "accepted_state_digest",
        "accepted_pit_dataset_ref",
        "accepted_pit_dataset_digest",
        "accepted_information_revision_registry_ref",
        "accepted_information_revision_registry_digest",
        "accepted_datum_revision_registry_ref",
        "accepted_datum_revision_registry_digest",
        "accepted_sentiment_state_digest",
        "accepted_sentiment_change_digest",
        "accepted_sentiment_state_ref",
        "accepted_graph_state_ref",
        "accepted_graph_state_digest",
        "accepted_hypothesis_registry_ref",
        "accepted_hypothesis_registry_digest",
        "accepted_expectation_ledger_ref",
        "accepted_expectation_ledger_digest",
        "accepted_probability_cloud_ref",
        "accepted_probability_cloud_digest",
        "accepted_probability_cloud_transition_digest",
        "last_completion_ref",
        "last_completion_digest",
        "assembly_bundle_bindings",
        "transport_evidence_bindings",
        *_GENESIS_BINDING_FIELDS,
        "failure_ref",
        "failure_digest",
        "resume_allowed",
        "created_at",
        "updated_at",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        "checkpoint_digest",
    }
)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31ResearchStoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ResearchStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V31ResearchStoreError(code)
    return parsed.astimezone(UTC)


def _text_or_failure_code(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31ResearchStoreError(code)
    return value.strip()


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


class LocalV31ResearchStore:
    """One local, content-addressed V3.1 run store."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.run_root / "checkpoint.json"
        # Process-local admission capabilities are issued only after the
        # Application layer has replayed the original semantic bundle.  A new
        # process must replay and register again before it can advance.
        self._semantic_admissions: dict[tuple[str, int], dict[str, str]] = {}

    def register_semantic_admission(
        self,
        *,
        run_id: str,
        cycle_index: int,
        artifact_digests: Mapping[str, str],
    ) -> None:
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or isinstance(cycle_index, bool)
            or not isinstance(cycle_index, int)
            or cycle_index < 1
            or set(artifact_digests) != _SEMANTIC_ADMISSION_KEYS
            or any(
                _HEX_64.fullmatch(str(artifact_digests.get(name) or "")) is None
                for name in _SEMANTIC_ADMISSION_KEYS
            )
        ):
            raise V31ResearchStoreError("V31_SEMANTIC_ADMISSION_INVALID")
        self._semantic_admissions[(run_id, cycle_index)] = {
            name: str(artifact_digests[name]) for name in _SEMANTIC_ADMISSION_KEYS
        }

    @contextmanager
    def _exclusive_lock(self, name: str):
        lock_path = self.run_root / ".locks" / f"{name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _safe_path(self, relative_ref: str) -> Path:
        candidate = Path(relative_ref)
        if candidate.is_absolute() or not candidate.parts or any(
            part in {"", ".", ".."} for part in candidate.parts
        ):
            raise V31ResearchStoreError("V31_ARTIFACT_REF_INVALID")
        cursor = self.run_root
        for part in candidate.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31ResearchStoreError("V31_ARTIFACT_REF_INVALID")
        target = (self.run_root / candidate).resolve()
        try:
            target.relative_to(self.run_root)
        except ValueError as exc:
            raise V31ResearchStoreError("V31_ARTIFACT_REF_INVALID") from exc
        return target

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]:
        """Persist source bytes write-once without interpreting their content."""

        if not isinstance(payload, bytes):
            raise V31ResearchStoreError("V31_RAW_BYTES_INVALID")
        target = self._safe_path(relative_ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise V31ResearchStoreError("V31_RAW_WRITE_ONCE_CONFLICT")
        else:
            try:
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            except FileExistsError as exc:
                if not target.is_file() or target.read_bytes() != payload:
                    raise V31ResearchStoreError(
                        "V31_RAW_WRITE_ONCE_CONFLICT"
                    ) from exc
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "relative_ref": relative_ref,
            "semantic_digest": digest,
            "physical_sha256": digest,
        }

    def read_raw(
        self,
        *,
        relative_ref: str,
        expected_sha256: str | None = None,
    ) -> bytes:
        target = self._safe_path(relative_ref)
        try:
            payload = target.read_bytes()
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise V31ResearchStoreError("V31_RAW_MISSING") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if (
            expected_sha256 is not None
            and (
                _HEX_64.fullmatch(expected_sha256) is None
                or digest != expected_sha256
            )
        ):
            raise V31ResearchStoreError("V31_RAW_DIGEST_MISMATCH")
        return payload

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]:
        target = self._safe_path(relative_ref)
        payload = dict(document)
        try:
            if digest_field in payload:
                semantic_digest = verify_self_digest(payload, digest_field)
            else:
                payload = self_digest(payload, digest_field)
                semantic_digest = str(payload[digest_field])
        except ValueError as exc:
            raise V31ResearchStoreError("V31_ARTIFACT_DIGEST_INVALID") from exc
        write_once_json(target, payload)
        return {
            "relative_ref": relative_ref,
            "semantic_digest": semantic_digest,
            "physical_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        target = self._safe_path(relative_ref)
        document = load_json_strict(target)
        try:
            digest = verify_self_digest(document, digest_field)
        except ValueError as exc:
            raise V31ResearchStoreError("V31_ARTIFACT_DIGEST_INVALID") from exc
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise V31ResearchStoreError("V31_ARTIFACT_DIGEST_MISMATCH")
        return document

    def discover_content_addressed_document(
        self,
        *,
        relative_dir: str,
        digest_field: str,
    ) -> Mapping[str, Any]:
        """Load the sole document whose filename is its semantic digest.

        Discovery is intentionally strict: missing, duplicate, extra, nested,
        or digest/name-mismatched entries are all ambiguous durable authority.
        """

        directory = self._safe_path(relative_dir)
        try:
            entries = sorted(directory.iterdir(), key=lambda value: value.name)
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise V31ResearchStoreError(
                "V31_CONTENT_ADDRESSED_DOCUMENT_MISSING"
            ) from exc
        if (
            len(entries) != 1
            or not entries[0].is_file()
            or entries[0].suffix != ".json"
            or _HEX_64.fullmatch(entries[0].stem) is None
        ):
            raise V31ResearchStoreError(
                "V31_CONTENT_ADDRESSED_DIRECTORY_AMBIGUOUS"
            )
        relative_ref = str(entries[0].relative_to(self.run_root))
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=entries[0].stem,
        )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        target = self._safe_path(relative_ref)
        return {
            "relative_ref": relative_ref,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    def _validate_assembly_bundle_document(
        self,
        document: Mapping[str, Any],
        *,
        run_id: str,
        cycle_index: int,
        expected_artifact_digests: Mapping[str, str] | None = None,
    ) -> str:
        """Validate the store-owned durable binding without decoding domain types.

        Typed-object reconstruction belongs to the Application layer.  The
        Infrastructure layer nevertheless rejects a missing, re-signed, or
        chronology-inconsistent bundle before a completed checkpoint can load.
        """

        try:
            digest = verify_self_digest(document, "assembly_bundle_digest")
        except ValueError as exc:
            raise V31ResearchStoreError("V31_ASSEMBLY_BUNDLE_DIGEST_INVALID") from exc
        artifact_digests = document.get("expected_artifact_digests")
        event_times = document.get("recorded_at_by_event")
        parameter_names = document.get("assembly_parameter_names")
        if (
            set(document) != _ASSEMBLY_BUNDLE_FIELDS
            or document.get("schema_id")
            != "theory_paper_v2_v31_durable_assembly_bundle"
            or document.get("schema_version") != "1.0.0"
            or document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
            or not isinstance(parameter_names, list)
            or not parameter_names
            or any(not isinstance(name, str) or not name for name in parameter_names)
            or document.get("assembly_signature_digest")
            != canonical_digest(parameter_names)
            or document.get("typed_assembly_inputs_digest")
            != canonical_digest(document.get("typed_assembly_inputs"))
            or not isinstance(artifact_digests, Mapping)
            or set(artifact_digests) != set(_EVENT_ORDER)
            or any(
                _HEX_64.fullmatch(str(artifact_digests.get(name) or "")) is None
                for name in _EVENT_ORDER
            )
            or not isinstance(event_times, Mapping)
            or set(event_times) != set(_EVENT_ORDER)
            or document.get("source_boundary")
            != "DURABLE_TYPED_INPUTS_ONLY_NO_CHAT_AUTHORITY"
            or document.get("chat_history_is_authority") is not False
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
        ):
            raise V31ResearchStoreError("V31_ASSEMBLY_BUNDLE_INVALID")
        _timestamp(document.get("decision_at"), "V31_ASSEMBLY_BUNDLE_TIME_INVALID")
        _timestamp(document.get("completed_at"), "V31_ASSEMBLY_BUNDLE_TIME_INVALID")
        times = [
            _timestamp(event_times[name], "V31_ASSEMBLY_BUNDLE_TIME_INVALID")
            for name in _EVENT_ORDER
        ]
        if any(current < previous for previous, current in zip(times, times[1:])):
            raise V31ResearchStoreError("V31_ASSEMBLY_BUNDLE_TIME_INVALID")
        if expected_artifact_digests is not None and (
            set(expected_artifact_digests) != set(_EVENT_ORDER)
            or any(
                artifact_digests[name] != expected_artifact_digests[name]
                for name in _EVENT_ORDER
            )
        ):
            raise V31ResearchStoreError(
                "V31_ASSEMBLY_BUNDLE_CHRONOLOGY_MISMATCH"
            )
        return digest

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        total_cycles: int,
        created_at: str,
        genesis_bindings: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        normalized_genesis: dict[str, str | None] = {
            field: None for field in _GENESIS_BINDING_FIELDS
        }
        if genesis_bindings is not None:
            if (
                not isinstance(genesis_bindings, Mapping)
                or set(genesis_bindings) != _GENESIS_BINDING_FIELDS
            ):
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_GENESIS_BINDING_INVALID"
                )
            for ref_name, digest_name in _GENESIS_BINDING_PAIRS:
                ref = genesis_bindings.get(ref_name)
                digest = genesis_bindings.get(digest_name)
                if (
                    not isinstance(ref, str)
                    or not ref
                    or _HEX_64.fullmatch(str(digest or "")) is None
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_GENESIS_BINDING_INVALID"
                    )
                self._safe_path(ref)
                normalized_genesis[ref_name] = ref
                normalized_genesis[digest_name] = str(digest)
        if self.checkpoint_path.exists():
            checkpoint = self.load_checkpoint(run_id=run_id)
            if genesis_bindings is not None and any(
                checkpoint.get(field) != normalized_genesis[field]
                for field in _GENESIS_BINDING_FIELDS
            ):
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_GENESIS_BINDING_CONFLICT"
                )
            return checkpoint
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or isinstance(total_cycles, bool)
            or not isinstance(total_cycles, int)
            or total_cycles < 1
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_INPUT_INVALID")
        _timestamp(created_at, "V31_CHECKPOINT_TIME_INVALID")
        checkpoint = self_digest(
            {
                "schema_id": "theory_paper_v31_research_checkpoint",
                "schema_version": "1.2.0",
                "run_id": run_id,
                "revision": 0,
                "status": "READY_FOR_CYCLE",
                "total_cycles": total_cycles,
                "completed_cycles": 0,
                "next_cycle_index": 1,
                "active_cycle_index": None,
                "accepted_state_ref": None,
                "accepted_state_digest": None,
                "accepted_pit_dataset_ref": None,
                "accepted_pit_dataset_digest": None,
                "accepted_information_revision_registry_ref": None,
                "accepted_information_revision_registry_digest": None,
                "accepted_datum_revision_registry_ref": None,
                "accepted_datum_revision_registry_digest": None,
                "accepted_sentiment_state_digest": None,
                "accepted_sentiment_change_digest": None,
                "accepted_sentiment_state_ref": None,
                "accepted_graph_state_ref": None,
                "accepted_graph_state_digest": None,
                "accepted_hypothesis_registry_ref": None,
                "accepted_hypothesis_registry_digest": None,
                "accepted_expectation_ledger_ref": None,
                "accepted_expectation_ledger_digest": None,
                "accepted_probability_cloud_ref": None,
                "accepted_probability_cloud_digest": None,
                "accepted_probability_cloud_transition_digest": None,
                "last_completion_ref": None,
                "last_completion_digest": None,
                "assembly_bundle_bindings": [],
                "transport_evidence_bindings": [],
                **normalized_genesis,
                "failure_ref": None,
                "failure_digest": None,
                "resume_allowed": True,
                "created_at": created_at,
                "updated_at": created_at,
                "chat_history_is_authority": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "checkpoint_digest",
        )
        write_once_json(self.checkpoint_path, checkpoint)
        return checkpoint

    def _validate_checkpoint(
        self,
        checkpoint: Mapping[str, Any],
        *,
        run_id: str,
        require_durable_bundle: bool = True,
    ) -> None:
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise V31ResearchStoreError("V31_CHECKPOINT_DIGEST_INVALID") from exc
        if (
            set(checkpoint) != _CHECKPOINT_FIELDS
            or checkpoint.get("schema_id") != "theory_paper_v31_research_checkpoint"
            or checkpoint.get("schema_version") != "1.2.0"
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("status") not in _CHECKPOINT_STATUSES
            or checkpoint.get("chat_history_is_authority") is not False
            or checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or checkpoint.get("executable") is not False
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_INVALID")
        populated_genesis_fields = {
            field
            for field in _GENESIS_BINDING_FIELDS
            if checkpoint.get(field) is not None
        }
        if populated_genesis_fields not in {frozenset(), _GENESIS_BINDING_FIELDS}:
            raise V31ResearchStoreError("V31_CHECKPOINT_GENESIS_BINDING_INVALID")
        authority_bound = bool(populated_genesis_fields)
        if authority_bound:
            for ref_name, digest_name in _GENESIS_BINDING_PAIRS:
                ref = checkpoint.get(ref_name)
                digest = checkpoint.get(digest_name)
                if (
                    not isinstance(ref, str)
                    or not ref
                    or _HEX_64.fullmatch(str(digest or "")) is None
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_GENESIS_BINDING_INVALID"
                    )
                self._safe_path(ref)
        for name in ("revision", "total_cycles", "completed_cycles", "next_cycle_index"):
            value = checkpoint.get(name)
            minimum = 0 if name in {"revision", "completed_cycles"} else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise V31ResearchStoreError("V31_CHECKPOINT_COUNTER_INVALID")
        total = int(checkpoint["total_cycles"])
        completed = int(checkpoint["completed_cycles"])
        if completed > total or int(checkpoint["next_cycle_index"]) != completed + 1:
            raise V31ResearchStoreError("V31_CHECKPOINT_COUNTER_INVALID")
        active = checkpoint.get("active_cycle_index")
        if active is not None and active != checkpoint["next_cycle_index"]:
            raise V31ResearchStoreError("V31_CHECKPOINT_ACTIVE_CYCLE_INVALID")
        if checkpoint["status"] == "CYCLE_IN_PROGRESS" and active is None:
            raise V31ResearchStoreError("V31_CHECKPOINT_ACTIVE_CYCLE_INVALID")
        if checkpoint["status"] != "CYCLE_IN_PROGRESS" and active is not None:
            raise V31ResearchStoreError("V31_CHECKPOINT_ACTIVE_CYCLE_INVALID")
        if checkpoint["status"] == "TERMINAL" and completed != total:
            raise V31ResearchStoreError("V31_CHECKPOINT_TERMINAL_INVALID")
        if checkpoint["status"] == "READY_FOR_CYCLE" and completed >= total:
            raise V31ResearchStoreError("V31_CHECKPOINT_READY_INVALID")
        for ref_name, digest_name in (
            ("accepted_state_ref", "accepted_state_digest"),
            ("accepted_pit_dataset_ref", "accepted_pit_dataset_digest"),
            (
                "accepted_information_revision_registry_ref",
                "accepted_information_revision_registry_digest",
            ),
            (
                "accepted_datum_revision_registry_ref",
                "accepted_datum_revision_registry_digest",
            ),
            (
                "accepted_sentiment_state_ref",
                "accepted_sentiment_state_digest",
            ),
            ("accepted_graph_state_ref", "accepted_graph_state_digest"),
            (
                "accepted_hypothesis_registry_ref",
                "accepted_hypothesis_registry_digest",
            ),
            (
                "accepted_expectation_ledger_ref",
                "accepted_expectation_ledger_digest",
            ),
            (
                "accepted_probability_cloud_ref",
                "accepted_probability_cloud_digest",
            ),
            ("last_completion_ref", "last_completion_digest"),
            ("failure_ref", "failure_digest"),
        ):
            ref = checkpoint.get(ref_name)
            digest = checkpoint.get(digest_name)
            if (ref is None) != (digest is None) or (
                ref is not None
                and (
                    not isinstance(ref, str)
                    or not ref
                    or not isinstance(digest, str)
                    or _HEX_64.fullmatch(digest) is None
                )
            ):
                raise V31ResearchStoreError("V31_CHECKPOINT_BINDING_INVALID")
        if checkpoint["status"] == "FAILED_CLOSED" and checkpoint["failure_ref"] is None:
            raise V31ResearchStoreError("V31_CHECKPOINT_FAILURE_BINDING_REQUIRED")
        if not isinstance(checkpoint.get("resume_allowed"), bool):
            raise V31ResearchStoreError("V31_CHECKPOINT_RESUME_FLAG_INVALID")
        if (
            checkpoint["status"] == "FAILED_CLOSED"
            and checkpoint["resume_allowed"] is not False
        ) or (
            checkpoint["status"] != "FAILED_CLOSED"
            and checkpoint["resume_allowed"] is not True
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_RESUME_FLAG_INCONSISTENT")
        if checkpoint["status"] != "FAILED_CLOSED" and checkpoint["failure_ref"] is not None:
            raise V31ResearchStoreError("V31_CHECKPOINT_FAILURE_BINDING_FORBIDDEN")
        if completed > 0 and (
            checkpoint["accepted_state_ref"] is None
            or checkpoint["accepted_pit_dataset_ref"] is None
            or checkpoint["accepted_information_revision_registry_ref"] is None
            or checkpoint["accepted_datum_revision_registry_ref"] is None
            or checkpoint["accepted_sentiment_state_ref"] is None
            or checkpoint["accepted_graph_state_ref"] is None
            or checkpoint["accepted_hypothesis_registry_ref"] is None
            or checkpoint["accepted_expectation_ledger_ref"] is None
            or checkpoint["accepted_probability_cloud_ref"] is None
            or checkpoint["last_completion_ref"] is None
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_COMPLETION_BINDING_INVALID")
        accepted_head_fields = (
            "accepted_pit_dataset_digest",
            "accepted_information_revision_registry_digest",
            "accepted_datum_revision_registry_digest",
            "accepted_sentiment_state_digest",
            "accepted_sentiment_change_digest",
            "accepted_graph_state_digest",
            "accepted_hypothesis_registry_digest",
            "accepted_expectation_ledger_digest",
            "accepted_probability_cloud_digest",
            "accepted_probability_cloud_transition_digest",
        )
        if completed == 0 and any(
            checkpoint.get(field) is not None for field in accepted_head_fields
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_STATE_HEAD_INVALID")
        if completed > 0 and any(
            not isinstance(checkpoint.get(field), str)
            or _HEX_64.fullmatch(str(checkpoint.get(field))) is None
            for field in accepted_head_fields
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_STATE_HEAD_INVALID")
        _timestamp(checkpoint["created_at"], "V31_CHECKPOINT_TIME_INVALID")
        _timestamp(checkpoint["updated_at"], "V31_CHECKPOINT_TIME_INVALID")
        if _timestamp(checkpoint["updated_at"], "V31_CHECKPOINT_TIME_INVALID") < _timestamp(
            checkpoint["created_at"], "V31_CHECKPOINT_TIME_INVALID"
        ):
            raise V31ResearchStoreError("V31_CHECKPOINT_TIME_INVALID")
        bundle_bindings = checkpoint.get("assembly_bundle_bindings")
        if (
            not isinstance(bundle_bindings, list)
            or (
                require_durable_bundle
                and len(bundle_bindings) != completed
            )
            or (
                not require_durable_bundle
                and len(bundle_bindings)
                not in {completed, max(0, completed - 1)}
            )
        ):
            raise V31ResearchStoreError(
                "V31_CHECKPOINT_ASSEMBLY_BUNDLE_BINDING_INVALID"
            )
        for expected_cycle, binding in enumerate(bundle_bindings, start=1):
            if (
                not isinstance(binding, Mapping)
                or set(binding) != {"cycle_index", "relative_ref", "semantic_digest"}
                or binding.get("cycle_index") != expected_cycle
                or _HEX_64.fullmatch(str(binding.get("semantic_digest") or ""))
                is None
            ):
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_ASSEMBLY_BUNDLE_BINDING_INVALID"
                )
            expected_bundle_ref = (
                f"cycles/{expected_cycle:04d}/assembly-bundles/"
                f"{binding['semantic_digest']}.json"
            )
            if binding.get("relative_ref") != expected_bundle_ref:
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_ASSEMBLY_BUNDLE_BINDING_INVALID"
                )
            if require_durable_bundle:
                events = self.read_events(
                    run_id=run_id, cycle_index=expected_cycle
                )
                if len(events) != len(_EVENT_ORDER):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_COMPLETION_EVIDENCE_MISSING"
                    )
                bundle = self.read_document(
                    relative_ref=expected_bundle_ref,
                    digest_field="assembly_bundle_digest",
                    expected_semantic_digest=str(binding["semantic_digest"]),
                )
                self._validate_assembly_bundle_document(
                    bundle,
                    run_id=run_id,
                    cycle_index=expected_cycle,
                    expected_artifact_digests={
                        event_type: str(
                            events[index]["artifact_semantic_digest"]
                        )
                        for index, event_type in enumerate(_EVENT_ORDER)
                    },
                )
        transport_bindings = checkpoint.get("transport_evidence_bindings")
        allowed_transport_lengths = (
            {completed}
            if require_durable_bundle
            else {completed, max(0, completed - 1)}
        )
        if (
            not isinstance(transport_bindings, list)
            or (
                authority_bound
                and len(transport_bindings) not in allowed_transport_lengths
            )
            or (not authority_bound and transport_bindings)
        ):
            raise V31ResearchStoreError(
                "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
            )
        for expected_cycle, binding in enumerate(transport_bindings, start=1):
            if (
                not isinstance(binding, Mapping)
                or set(binding) != _TRANSPORT_EVIDENCE_BINDING_FIELDS
                or binding.get("cycle_index") != expected_cycle
                or _HEX_64.fullmatch(
                    str(binding.get("semantic_digest") or "")
                )
                is None
                or _HEX_64.fullmatch(
                    str(binding.get("physical_sha256") or "")
                )
                is None
            ):
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
                )
            expected_ref = (
                f"cycles/{expected_cycle:04d}/transport-evidence/"
                f"{binding['semantic_digest']}.json"
            )
            if binding.get("relative_ref") != expected_ref:
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
                )
            if require_durable_bundle:
                evidence = self.read_document(
                    relative_ref=expected_ref,
                    digest_field="transport_evidence_digest",
                    expected_semantic_digest=str(binding["semantic_digest"]),
                )
                target = self._safe_path(expected_ref)
                if (
                    hashlib.sha256(target.read_bytes()).hexdigest()
                    != binding["physical_sha256"]
                    or evidence.get("schema_id")
                    != "theory_paper_v31_agent_transport_evidence"
                    or evidence.get("schema_version") != "1.0.0"
                    or evidence.get("run_id") != run_id
                    or evidence.get("cycle_index") != expected_cycle
                    or evidence.get("external_execution_authority")
                    != "NONE_LOCAL_SIMULATION"
                    or evidence.get("executable") is not False
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
                    )
        if checkpoint["status"] == "FAILED_CLOSED":
            failure = self.read_document(
                relative_ref=str(checkpoint["failure_ref"]),
                digest_field="failure_digest",
                expected_semantic_digest=str(checkpoint["failure_digest"]),
            )
            self._validate_failure_document(
                failure,
                run_id=run_id,
                expected_cycle_index=int(checkpoint["next_cycle_index"]),
            )
            if (
                failure["occurred_at"] != checkpoint["updated_at"]
                or failure["resume_allowed"] is not False
            ):
                raise V31ResearchStoreError(
                    "V31_CHECKPOINT_FAILURE_BINDING_INVALID"
                )

    def _validate_failure_document(
        self,
        document: Mapping[str, Any],
        *,
        run_id: str,
        expected_cycle_index: int,
    ) -> str:
        try:
            digest = verify_self_digest(document, "failure_digest")
        except ValueError as exc:
            raise V31ResearchStoreError("V31_FAILURE_DIGEST_INVALID") from exc
        if (
            set(document) != _FAILURE_FIELDS
            or document.get("schema_id")
            != "theory_paper_v31_research_failure"
            or document.get("schema_version") != "1.0.0"
            or document.get("run_id") != run_id
            or document.get("cycle_index") != expected_cycle_index
            or not isinstance(document.get("event_prefix_length"), int)
            or isinstance(document.get("event_prefix_length"), bool)
            or not 0 <= int(document["event_prefix_length"]) <= len(_EVENT_ORDER)
            or not isinstance(document.get("failure_code"), str)
            or not str(document["failure_code"]).strip()
            or not isinstance(document.get("failure_summary"), str)
            or not str(document["failure_summary"]).strip()
            or _HEX_64.fullmatch(
                str(document.get("checkpoint_digest_before_failure") or "")
            )
            is None
            or document.get("resume_allowed") is not False
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
        ):
            raise V31ResearchStoreError("V31_FAILURE_DOCUMENT_INVALID")
        last_event_digest = document.get("last_event_digest")
        if (
            (document["event_prefix_length"] == 0 and last_event_digest is not None)
            or (
                document["event_prefix_length"] > 0
                and _HEX_64.fullmatch(str(last_event_digest or "")) is None
            )
        ):
            raise V31ResearchStoreError("V31_FAILURE_EVENT_PREFIX_INVALID")
        _timestamp(document.get("occurred_at"), "V31_FAILURE_TIME_INVALID")
        return digest

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        checkpoint = load_json_strict(self.checkpoint_path)
        self._validate_checkpoint(checkpoint, run_id=run_id)
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        with self._exclusive_lock("checkpoint"):
            current = self.load_checkpoint(run_id=run_id)
            if current["checkpoint_digest"] != expected_checkpoint_digest:
                raise V31ResearchStoreError("V31_CHECKPOINT_COMPARE_SWAP_FAILED")
            if current["status"] in {"TERMINAL", "FAILED_CLOSED"}:
                raise V31ResearchStoreError("V31_CHECKPOINT_TERMINAL_TRANSITION_FORBIDDEN")
            candidate = self_digest(dict(checkpoint), "checkpoint_digest")
            self._validate_checkpoint(
                candidate,
                run_id=run_id,
                require_durable_bundle=False,
            )
            if (
                candidate["revision"] != current["revision"] + 1
                or candidate["total_cycles"] != current["total_cycles"]
                or candidate["created_at"] != current["created_at"]
                or any(
                    candidate[field] != current[field]
                    for field in _GENESIS_BINDING_FIELDS
                )
                or candidate["completed_cycles"]
                not in {current["completed_cycles"], current["completed_cycles"] + 1}
                or _timestamp(candidate["updated_at"], "V31_CHECKPOINT_TIME_INVALID")
                < _timestamp(current["updated_at"], "V31_CHECKPOINT_TIME_INVALID")
            ):
                raise V31ResearchStoreError("V31_CHECKPOINT_TRANSITION_INVALID")
            advanced = candidate["completed_cycles"] == current["completed_cycles"] + 1
            if current["status"] == "READY_FOR_CYCLE" and candidate["status"] not in {
                "CYCLE_IN_PROGRESS",
                "FAILED_CLOSED",
            }:
                raise V31ResearchStoreError("V31_CHECKPOINT_TRANSITION_INVALID")
            if current["status"] == "CYCLE_IN_PROGRESS" and (
                (advanced and candidate["status"] not in {"READY_FOR_CYCLE", "TERMINAL"})
                or (
                    not advanced
                    and candidate["status"] not in {"CYCLE_IN_PROGRESS", "FAILED_CLOSED"}
                )
            ):
                raise V31ResearchStoreError("V31_CHECKPOINT_TRANSITION_INVALID")
            if candidate["status"] == "FAILED_CLOSED":
                failure = self.read_document(
                    relative_ref=str(candidate["failure_ref"]),
                    digest_field="failure_digest",
                    expected_semantic_digest=str(candidate["failure_digest"]),
                )
                self._validate_failure_document(
                    failure,
                    run_id=run_id,
                    expected_cycle_index=int(current["next_cycle_index"]),
                )
                current_events = self.read_events(
                    run_id=run_id,
                    cycle_index=int(current["next_cycle_index"]),
                )
                if (
                    failure["checkpoint_digest_before_failure"]
                    != current["checkpoint_digest"]
                    or failure["event_prefix_length"] != len(current_events)
                    or failure["last_event_digest"]
                    != (None if not current_events else current_events[-1]["event_digest"])
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_FAILURE_BINDING_INVALID"
                    )
            if not advanced and any(
                candidate[name] != current[name]
                for name in (
                    "accepted_state_ref",
                    "accepted_state_digest",
                    "accepted_pit_dataset_ref",
                    "accepted_pit_dataset_digest",
                    "accepted_information_revision_registry_ref",
                    "accepted_information_revision_registry_digest",
                    "accepted_datum_revision_registry_ref",
                    "accepted_datum_revision_registry_digest",
                    "accepted_sentiment_state_digest",
                    "accepted_sentiment_change_digest",
                    "accepted_sentiment_state_ref",
                    "accepted_graph_state_ref",
                    "accepted_graph_state_digest",
                    "accepted_hypothesis_registry_ref",
                    "accepted_hypothesis_registry_digest",
                    "accepted_expectation_ledger_ref",
                    "accepted_expectation_ledger_digest",
                    "accepted_probability_cloud_ref",
                    "accepted_probability_cloud_digest",
                    "accepted_probability_cloud_transition_digest",
                    "last_completion_ref",
                    "last_completion_digest",
                    "assembly_bundle_bindings",
                    "transport_evidence_bindings",
                )
            ):
                raise V31ResearchStoreError("V31_CHECKPOINT_ACCEPTED_HEAD_MUTATION_FORBIDDEN")
            if advanced:
                completed_cycle = int(candidate["completed_cycles"])
                if (
                    completed_cycle != current["next_cycle_index"]
                    or candidate["status"]
                    not in {"READY_FOR_CYCLE", "TERMINAL"}
                ):
                    raise V31ResearchStoreError("V31_CHECKPOINT_TRANSITION_INVALID")
                events = self.read_events(run_id=run_id, cycle_index=completed_cycle)
                if len(events) != len(_EVENT_ORDER):
                    raise V31ResearchStoreError("V31_CHECKPOINT_COMPLETION_EVIDENCE_MISSING")
                semantic_admission = self._semantic_admissions.get(
                    (run_id, completed_cycle)
                )
                if semantic_admission is None or any(
                    semantic_admission.get(event_type)
                    != events[index]["artifact_semantic_digest"]
                    for index, event_type in enumerate(_EVENT_ORDER)
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_SEMANTIC_VERIFICATION_REQUIRED"
                    )
                bundle_ref = (
                    f"cycles/{completed_cycle:04d}/assembly-bundles/"
                    f"{semantic_admission['ASSEMBLY_BUNDLE']}.json"
                )
                bundle = self.read_document(
                    relative_ref=bundle_ref,
                    digest_field="assembly_bundle_digest",
                    expected_semantic_digest=semantic_admission[
                        "ASSEMBLY_BUNDLE"
                    ],
                )
                bundle_digest = self._validate_assembly_bundle_document(
                    bundle,
                    run_id=run_id,
                    cycle_index=completed_cycle,
                    expected_artifact_digests={
                        event_type: str(
                            events[index]["artifact_semantic_digest"]
                        )
                        for index, event_type in enumerate(_EVENT_ORDER)
                    },
                )
                expected_bundle_bindings = [
                    *current["assembly_bundle_bindings"],
                    {
                        "cycle_index": completed_cycle,
                        "relative_ref": bundle_ref,
                        "semantic_digest": bundle_digest,
                    },
                ]
                authority_bound = all(
                    current.get(field) is not None
                    for field in _GENESIS_BINDING_FIELDS
                )
                if authority_bound:
                    transport_bindings = candidate["transport_evidence_bindings"]
                    if (
                        len(transport_bindings)
                        != len(current["transport_evidence_bindings"]) + 1
                        or transport_bindings[:-1]
                        != current["transport_evidence_bindings"]
                        or transport_bindings[-1].get("cycle_index")
                        != completed_cycle
                    ):
                        raise V31ResearchStoreError(
                            "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
                        )
                elif (
                    candidate["transport_evidence_bindings"]
                    != current["transport_evidence_bindings"]
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_TRANSPORT_EVIDENCE_BINDING_INVALID"
                    )
                accepted = events[-2]
                completion = events[-1]
                if (
                    candidate["accepted_state_ref"] != accepted["artifact_ref"]
                    or candidate["accepted_state_digest"]
                    != accepted["artifact_semantic_digest"]
                    or candidate["last_completion_ref"] != completion["artifact_ref"]
                    or candidate["last_completion_digest"]
                    != completion["artifact_semantic_digest"]
                    or candidate["assembly_bundle_bindings"]
                    != expected_bundle_bindings
                ):
                    raise V31ResearchStoreError("V31_CHECKPOINT_COMPLETION_BINDING_INVALID")
                accepted_document = self.read_document(
                    relative_ref=accepted["artifact_ref"],
                    digest_field="accepted_state_digest",
                    expected_semantic_digest=accepted[
                        "artifact_semantic_digest"
                    ],
                )
                for checkpoint_field, accepted_field in (
                    ("accepted_pit_dataset_digest", "pit_dataset_digest"),
                    (
                        "accepted_information_revision_registry_digest",
                        "information_revision_registry_digest",
                    ),
                    (
                        "accepted_datum_revision_registry_digest",
                        "datum_revision_registry_digest",
                    ),
                    (
                        "accepted_sentiment_state_digest",
                        "sentiment_state_digest",
                    ),
                    (
                        "accepted_sentiment_change_digest",
                        "sentiment_change_digest",
                    ),
                    ("accepted_graph_state_digest", "graph_state_digest"),
                    (
                        "accepted_hypothesis_registry_digest",
                        "hypothesis_registry_digest",
                    ),
                    (
                        "accepted_expectation_ledger_digest",
                        "expectation_ledger_digest",
                    ),
                    (
                        "accepted_probability_cloud_digest",
                        "probability_cloud_digest",
                    ),
                    (
                        "accepted_probability_cloud_transition_digest",
                        "probability_cloud_transition_digest",
                    ),
                ):
                    if candidate.get(checkpoint_field) != accepted_document.get(
                        accepted_field
                    ):
                        raise V31ResearchStoreError(
                            "V31_CHECKPOINT_STATE_HEAD_INVALID"
                        )
                information_registry = self.read_document(
                    relative_ref=str(
                        candidate["accepted_information_revision_registry_ref"]
                    ),
                    digest_field="information_revision_registry_digest",
                    expected_semantic_digest=str(
                        candidate["accepted_information_revision_registry_digest"]
                    ),
                )
                datum_registry = self.read_document(
                    relative_ref=str(
                        candidate["accepted_datum_revision_registry_ref"]
                    ),
                    digest_field="datum_revision_registry_digest",
                    expected_semantic_digest=str(
                        candidate["accepted_datum_revision_registry_digest"]
                    ),
                )
                accepted_head_documents = {
                    "pit_dataset": self.read_document(
                        relative_ref=str(candidate["accepted_pit_dataset_ref"]),
                        digest_field="dataset_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_pit_dataset_digest"]
                        ),
                    ),
                    "sentiment_state": self.read_document(
                        relative_ref=str(
                            candidate["accepted_sentiment_state_ref"]
                        ),
                        digest_field="sentiment_state_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_sentiment_state_digest"]
                        ),
                    ),
                    "graph_state": self.read_document(
                        relative_ref=str(candidate["accepted_graph_state_ref"]),
                        digest_field="graph_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_graph_state_digest"]
                        ),
                    ),
                    "hypothesis_registry": self.read_document(
                        relative_ref=str(
                            candidate["accepted_hypothesis_registry_ref"]
                        ),
                        digest_field="hypothesis_registry_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_hypothesis_registry_digest"]
                        ),
                    ),
                    "expectation_ledger": self.read_document(
                        relative_ref=str(
                            candidate["accepted_expectation_ledger_ref"]
                        ),
                        digest_field="expectation_ledger_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_expectation_ledger_digest"]
                        ),
                    ),
                    "probability_cloud": self.read_document(
                        relative_ref=str(
                            candidate["accepted_probability_cloud_ref"]
                        ),
                        digest_field="cloud_digest",
                        expected_semantic_digest=str(
                            candidate["accepted_probability_cloud_digest"]
                        ),
                    ),
                }
                if (
                    information_registry.get("schema_id")
                    != "theory_paper_v2_v31_information_revision_registry"
                    or datum_registry.get("schema_id")
                    != "theory_paper_v2_v31_datum_revision_registry"
                    or information_registry.get("external_execution_authority")
                    != "NONE_LOCAL_SIMULATION"
                    or datum_registry.get("external_execution_authority")
                    != "NONE_LOCAL_SIMULATION"
                    or information_registry.get("executable") is not False
                    or datum_registry.get("executable") is not False
                    or information_registry.get("run_id") != run_id
                    or information_registry.get("cycle_index") != completed_cycle
                    or datum_registry.get("run_id") != run_id
                    or datum_registry.get("cycle_index") != completed_cycle
                    or accepted_head_documents["pit_dataset"].get("schema_id")
                    != "theory_paper_v2_v31_point_in_time_dataset"
                    or accepted_head_documents["sentiment_state"].get(
                        "schema_id"
                    )
                    != "theory_paper_v2_v31_multidimensional_market_sentiment_state"
                    or accepted_head_documents["hypothesis_registry"].get(
                        "schema_id"
                    )
                    != "dynamic_hypothesis_registry"
                    or accepted_head_documents["expectation_ledger"].get(
                        "schema_id"
                    )
                    != "append_only_expectation_ledger"
                    or accepted_head_documents["probability_cloud"].get(
                        "schema_id"
                    )
                    != "theory_paper_v2_v31_probability_cloud"
                    or any(
                        "executable" in document
                        and document.get("executable") is not False
                        for name, document in accepted_head_documents.items()
                        if name != "graph_state"
                    )
                ):
                    raise V31ResearchStoreError(
                        "V31_CHECKPOINT_REGISTRY_BINDING_INVALID"
                    )
            _atomic_json(self.checkpoint_path, candidate)
            if advanced:
                self._semantic_admissions.pop((run_id, completed_cycle), None)
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
        """Record one explicit permanent failure and make resumption impossible."""

        checkpoint = self.load_checkpoint(run_id=run_id)
        if checkpoint["checkpoint_digest"] != expected_checkpoint_digest:
            raise V31ResearchStoreError("V31_CHECKPOINT_COMPARE_SWAP_FAILED")
        if checkpoint["status"] not in {"READY_FOR_CYCLE", "CYCLE_IN_PROGRESS"}:
            raise V31ResearchStoreError("V31_CHECKPOINT_FAILURE_TRANSITION_FORBIDDEN")
        _timestamp(occurred_at, "V31_FAILURE_TIME_INVALID")
        cycle_index = int(checkpoint["next_cycle_index"])
        events = self.read_events(run_id=run_id, cycle_index=cycle_index)
        failure = self_digest(
            {
                "schema_id": "theory_paper_v31_research_failure",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "occurred_at": occurred_at,
                "failure_code": _text_or_failure_code(
                    failure_code, "V31_FAILURE_CODE_INVALID"
                ),
                "failure_summary": _text_or_failure_code(
                    failure_summary, "V31_FAILURE_SUMMARY_INVALID"
                ),
                "checkpoint_digest_before_failure": checkpoint[
                    "checkpoint_digest"
                ],
                "event_prefix_length": len(events),
                "last_event_digest": None if not events else events[-1]["event_digest"],
                "resume_allowed": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "failure_digest",
        )
        relative_ref = (
            f"failures/cycle-{cycle_index:04d}-"
            f"checkpoint-{int(checkpoint['revision']):04d}.json"
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
                "active_cycle_index": None,
                "failure_ref": binding["relative_ref"],
                "failure_digest": binding["semantic_digest"],
                "resume_allowed": False,
                "updated_at": occurred_at,
            },
        )

    def _event_root(self, cycle_index: int) -> Path:
        if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
            raise V31ResearchStoreError("V31_EVENT_CYCLE_INVALID")
        return self.run_root / "events" / f"cycle-{cycle_index:04d}"

    def _verify_contract_document(
        self,
        *,
        event_type: str,
        document: Mapping[str, Any],
        run_id: str,
        cycle_index: int,
        semantic_digest: str,
    ) -> str:
        """Verify the formal artifact assigned to one chronology event.

        A self-signed JSON object is not sufficient.  The event fixes the exact
        schema, digest field, research-only authority boundary, and cycle
        identity that may occupy that position in the chronology.
        """

        try:
            schema_id, digest_field, authority = _EVENT_CONTRACT[event_type]
        except KeyError as exc:  # pragma: no cover - guarded by event order
            raise V31ResearchStoreError("V31_EVENT_TYPE_INVALID") from exc
        if (
            document.get("schema_id") != schema_id
            or document.get("schema_version") != "1.0.0"
            or document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
            or document.get("external_execution_authority") != authority
            or document.get("executable") is not False
        ):
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID")
        if event_type in _DOCUMENT_FIELDS and set(document) != _DOCUMENT_FIELDS[event_type]:
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_SCHEMA_INVALID")
        try:
            supplied = verify_self_digest(document, digest_field)
        except ValueError as exc:
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_SEMANTIC_DRIFT") from exc
        if supplied != semantic_digest:
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_SEMANTIC_DRIFT")
        try:
            if event_type == "INPUTS_ADMITTED":
                verify_v31_inputs_receipt(document)
            elif event_type == "PROPOSAL_SEALED":
                # The input receipt is checked with the complete prefix below.
                if set(document) != {
                    "schema_id", "schema_version", "run_id", "cycle_index",
                    "decision_at", "symbol", "inputs_receipt_digest",
                    "graph_delta_digest", "hypothesis_registry_digest",
                    "expectation_ledger_digest", "probability_cloud_digest",
                    "scenario_path_set_digest", "sentiment_state_digest",
                    "sentiment_change_digest", "candidate_bindings",
                    "information_interpretations", "competing_explanations",
                    "unknowns", "requested_observations",
                    "hypothesis_novelty_rationales", "limitations",
                    "proposal_phase", "selection_fields_admitted",
                    "external_execution_authority", "executable",
                    "agent_proposal_digest",
                }:
                    raise V31ResearchStoreError("V31_EVENT_ARTIFACT_SCHEMA_INVALID")
        except AgentResearchContractError as exc:
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID") from exc

        if event_type == "EVALUATION_SEALED":
            bindings = {field: document[field] for field in _PRESELECTION_BINDING_FIELDS}
            _timestamp(document.get("decision_at"), "V31_DECISION_TIME_INVALID")
            path_evaluation = document.get("path_evaluation")
            probability_transition = document.get(
                "probability_cloud_transition"
            )
            candidate_admissibility = document.get(
                "candidate_path_admissibility"
            )
            try:
                path_evaluation_digest = verify_self_digest(
                    path_evaluation, "path_evaluation_digest"
                )
                probability_transition_digest = verify_self_digest(
                    probability_transition,
                    "probability_cloud_transition_digest",
                )
            except (TypeError, ValueError) as exc:
                raise V31ResearchStoreError(
                    "V31_EVENT_ARTIFACT_CONTRACT_INVALID"
                ) from exc
            expected_dynamic_binding = canonical_digest(
                {
                    "run_id": document["run_id"],
                    "cycle_index": document["cycle_index"],
                    "decision_at": document["decision_at"],
                    "hypothesis_registry_digest": document[
                        "hypothesis_registry_digest"
                    ],
                    "expectation_ledger_digest": document[
                        "expectation_ledger_digest"
                    ],
                }
            )
            if (
                canonical_digest(bindings) != document.get("artifact_bindings_digest")
                or document.get("dynamic_research_binding_digest")
                != expected_dynamic_binding
                or document.get("binding_order") != list(_BINDING_ORDER)
                or document.get("selection_fields_admitted") is not False
                or document.get("graph_chain_policy")
                != "STRICT_ADJACENT_EPISTEMIC_STAGES"
                or path_evaluation_digest
                != document.get("path_evaluation_digest")
                or probability_transition_digest
                != document.get("probability_cloud_transition_digest")
                or probability_transition.get("updated_cloud_digest")
                != document.get("probability_cloud_digest")
                or probability_transition.get("cycle_index")
                != document.get("cycle_index")
                or probability_transition.get("executable") is not False
                or path_evaluation.get("path_set_digest")
                != document.get("scenario_path_set_digest")
                or path_evaluation.get("false_supports_action") is not False
                or path_evaluation.get("unknown_supports_non_wait_action")
                is not False
                or not isinstance(candidate_admissibility, list)
                or not candidate_admissibility
                or canonical_digest(candidate_admissibility)
                != document.get("candidate_path_admissibility_digest")
                or document.get("selectable_candidate_ids")
                != [
                    row.get("candidate_id")
                    for row in candidate_admissibility
                    if row.get("selectable")
                ]
            ):
                raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID")
        elif event_type == "SELECTION_SEALED" and (
            not isinstance(document.get("selected_candidate_id"), str)
            or not str(document.get("selected_candidate_id") or "").strip()
            or not isinstance(document.get("reason"), str)
            or not str(document.get("reason") or "").strip()
            or not isinstance(document.get("failure_conditions"), list)
            or not document.get("failure_conditions")
            or _timestamp(
                document.get("next_review_at"), "V31_SELECTION_REVIEW_TIME_INVALID"
            )
            < _timestamp(
                document.get("selected_at"), "V31_SELECTION_TIME_INVALID"
            )
        ):
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID")
        elif event_type == "STATE_ACCEPTED" and (
            document.get("status") != "ACCEPTED_RESEARCH_ONLY"
            or document.get("selection_boundary")
            != "SEPARATE_AFTER_COMPLETE_EVALUATION"
            or document.get("dynamic_research_binding_digest")
            != canonical_digest(
                {
                    "run_id": document["run_id"],
                    "cycle_index": document["cycle_index"],
                    "decision_at": document["decision_at"],
                    "hypothesis_registry_digest": document[
                        "hypothesis_registry_digest"
                    ],
                    "expectation_ledger_digest": document[
                        "expectation_ledger_digest"
                    ],
                }
            )
            or _timestamp(
                document.get("selected_at"), "V31_SELECTION_TIME_INVALID"
            )
            < _timestamp(
                document.get("decision_at"), "V31_DECISION_TIME_INVALID"
            )
        ):
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID")
        elif event_type == "COMPLETION_SEALED":
            if (
                document.get("completion_status") != "COMPLETE_RESEARCH_ONLY"
                or document.get("dynamic_research_binding_digest")
                != canonical_digest(
                    {
                        "run_id": document["run_id"],
                        "cycle_index": document["cycle_index"],
                        "decision_at": document["decision_at"],
                        "hypothesis_registry_digest": document[
                            "hypothesis_registry_digest"
                        ],
                        "expectation_ledger_digest": document[
                            "expectation_ledger_digest"
                        ],
                    }
                )
                or _timestamp(
                    document.get("completed_at"), "V31_COMPLETION_TIME_INVALID"
                )
                < _timestamp(
                    document.get("selected_at"), "V31_SELECTION_TIME_INVALID"
                )
            ):
                raise V31ResearchStoreError("V31_EVENT_ARTIFACT_CONTRACT_INVALID")
        return digest_field

    def _verify_cross_stage_documents(
        self,
        *,
        run_id: str,
        cycle_index: int,
        documents: Sequence[Mapping[str, Any]],
    ) -> None:
        """Rebuild the digest links across every available chronology prefix."""

        if not documents:
            return
        inputs = documents[0]
        if cycle_index == 1:
            if any(
                inputs.get(field) is not None
                for field in (
                    "previous_accepted_state_digest",
                    "previous_information_revision_registry_digest",
                    "previous_datum_revision_registry_digest",
                )
            ):
                raise V31ResearchStoreError("V31_INPUT_PREVIOUS_STATE_BINDING_INVALID")
        else:
            prior_events = self.read_events(run_id=run_id, cycle_index=cycle_index - 1)
            if len(prior_events) != len(_EVENT_ORDER):
                raise V31ResearchStoreError("V31_INPUT_PREVIOUS_STATE_BINDING_INVALID")
            if (
                inputs.get("previous_accepted_state_digest")
                != prior_events[-2]["artifact_semantic_digest"]
            ):
                raise V31ResearchStoreError("V31_INPUT_PREVIOUS_STATE_BINDING_INVALID")
            prior_accepted = self.read_document(
                relative_ref=prior_events[-2]["artifact_ref"],
                digest_field="accepted_state_digest",
                expected_semantic_digest=prior_events[-2][
                    "artifact_semantic_digest"
                ],
            )
            for input_field, accepted_field in (
                ("prior_graph_digest", "graph_state_digest"),
                (
                    "previous_information_revision_registry_digest",
                    "information_revision_registry_digest",
                ),
                ("previous_pit_dataset_digest", "pit_dataset_digest"),
                (
                    "previous_datum_revision_registry_digest",
                    "datum_revision_registry_digest",
                ),
                (
                    "previous_hypothesis_registry_digest",
                    "hypothesis_registry_digest",
                ),
                (
                    "previous_expectation_ledger_digest",
                    "expectation_ledger_digest",
                ),
                (
                    "previous_probability_cloud_digest",
                    "probability_cloud_digest",
                ),
            ):
                if inputs.get(input_field) != prior_accepted.get(accepted_field):
                    raise V31ResearchStoreError(
                        "V31_INPUT_PREVIOUS_HEAD_BINDING_INVALID"
                    )
        if len(documents) >= 2:
            proposal = documents[1]
            try:
                verify_v31_agent_proposal(proposal, inputs_receipt=inputs)
            except AgentResearchContractError as exc:
                raise V31ResearchStoreError("V31_PROPOSAL_INPUT_BINDING_INVALID") from exc
            for field in ("run_id", "cycle_index", "decision_at", "symbol"):
                if proposal.get(field) != inputs.get(field):
                    raise V31ResearchStoreError("V31_CYCLE_IDENTITY_BINDING_INVALID")
        if len(documents) >= 3:
            proposal = documents[1]
            preselection = documents[2]
            for field in ("run_id", "cycle_index", "decision_at", "symbol"):
                if preselection.get(field) != inputs.get(field):
                    raise V31ResearchStoreError("V31_CYCLE_IDENTITY_BINDING_INVALID")
            for proposal_field, preselection_field in (
                ("graph_delta_digest", "graph_delta_digest"),
                ("hypothesis_registry_digest", "hypothesis_registry_digest"),
                ("expectation_ledger_digest", "expectation_ledger_digest"),
                ("probability_cloud_digest", "probability_cloud_digest"),
                ("scenario_path_set_digest", "scenario_path_set_digest"),
            ):
                if proposal.get(proposal_field) != preselection.get(preselection_field):
                    raise V31ResearchStoreError("V31_PROPOSAL_EVALUATION_BINDING_INVALID")
            if (
                preselection.get("inputs_receipt_digest")
                != inputs.get("inputs_receipt_digest")
                or preselection.get("agent_proposal_digest")
                != proposal.get("agent_proposal_digest")
            ):
                raise V31ResearchStoreError(
                    "V31_PROPOSAL_EVALUATION_BINDING_INVALID"
                )
            for input_field, preselection_field in (
                ("information_event_digests", "information_event_digests"),
                (
                    "information_revision_registry_digest",
                    "information_revision_registry_digest",
                ),
                (
                    "association_estimation_receipt_digests",
                    "association_estimation_receipt_digests",
                ),
                ("pit_dataset_digest", "pit_dataset_digest"),
                (
                    "datum_revision_registry_digest",
                    "datum_revision_registry_digest",
                ),
                ("prior_graph_digest", "prior_graph_digest"),
            ):
                if inputs.get(input_field) != preselection.get(preselection_field):
                    raise V31ResearchStoreError("V31_INPUT_EVALUATION_BINDING_INVALID")
            proposal_candidate_bindings = {
                str(row.get("candidate_id")): row.get(
                    "candidate_proposal_digest"
                )
                for row in preselection.get(
                    "candidate_path_admissibility", []
                )
                if isinstance(row, Mapping)
            }
            if proposal_candidate_bindings != proposal.get("candidate_bindings"):
                raise V31ResearchStoreError(
                    "V31_PROPOSAL_EVALUATION_BINDING_INVALID"
                )
        if len(documents) >= 4:
            preselection = documents[2]
            selection = documents[3]
            candidate_rows = {
                str(row.get("candidate_id")): row
                for row in preselection.get("candidate_path_admissibility", [])
                if isinstance(row, Mapping)
            }
            selected_row = candidate_rows.get(
                str(selection.get("selected_candidate_id") or "")
            )
            if (
                selection.get("run_id") != run_id
                or selection.get("cycle_index") != cycle_index
                or selection.get("action_evaluation_digest")
                != preselection.get("action_evaluation_digest")
                or selection.get("selected_candidate_id")
                not in preselection.get("selectable_candidate_ids", [])
                or selected_row is None
                or selection.get("selected_action") != selected_row.get("action")
                or set(selection.get("alternative_explanations", {}))
                != set(candidate_rows) - {selection.get("selected_candidate_id")}
                or _timestamp(
                    selection.get("selected_at"), "V31_SELECTION_TIME_INVALID"
                )
                < _timestamp(
                    preselection.get("decision_at"), "V31_DECISION_TIME_INVALID"
                )
            ):
                raise V31ResearchStoreError("V31_SELECTION_EVALUATION_BINDING_INVALID")
        if len(documents) >= 5:
            proposal, preselection, selection, accepted = (
                documents[1], documents[2], documents[3], documents[4]
            )
            if any(
                accepted.get(field) != preselection.get(field)
                for field in (
                    "run_id", "cycle_index", "decision_at", "symbol",
                    "inputs_receipt_digest",
                    "artifact_bindings_digest",
                    "information_revision_registry_digest",
                    "datum_revision_registry_digest",
                    "hypothesis_registry_digest",
                    "expectation_ledger_digest", "dynamic_research_binding_digest",
                    "pit_dataset_digest", "graph_state_digest",
                    "probability_cloud_digest",
                    "probability_cloud_transition_digest",
                    "scenario_path_set_digest", "path_evaluation_digest",
                    "action_evaluation_digest",
                )
            ) or (
                accepted.get("preselection_digest")
                != preselection.get("preselection_digest")
                or accepted.get("action_selection_digest")
                != selection.get("action_selection_digest")
                or accepted.get("agent_proposal_digest")
                != proposal.get("agent_proposal_digest")
                or accepted.get("selected_candidate_id")
                != selection.get("selected_candidate_id")
                or accepted.get("selected_at") != selection.get("selected_at")
                or accepted.get("selected_candidate_evaluation_digest")
                != next(
                    (
                        row.get("candidate_binding_digest")
                        for row in preselection.get(
                            "candidate_path_admissibility", []
                        )
                        if row.get("candidate_id")
                        == accepted.get("selected_candidate_id")
                    ),
                    None,
                )
            ):
                raise V31ResearchStoreError("V31_ACCEPTED_STATE_CHAIN_BINDING_INVALID")
        if len(documents) >= 6:
            preselection, selection, accepted, completion = (
                documents[2], documents[3], documents[4], documents[5]
            )
            if any(
                completion.get(field) != accepted.get(field)
                for field in (
                    "run_id", "cycle_index", "decision_at", "selected_at",
                    "inputs_receipt_digest",
                    "preselection_digest", "artifact_bindings_digest",
                    "pit_dataset_digest",
                    "information_revision_registry_digest",
                    "datum_revision_registry_digest",
                    "graph_state_digest",
                    "hypothesis_registry_digest", "expectation_ledger_digest",
                    "dynamic_research_binding_digest",
                    "probability_cloud_digest",
                    "probability_cloud_transition_digest",
                    "scenario_path_set_digest", "path_evaluation_digest",
                    "action_selection_digest",
                    "selected_candidate_id",
                )
            ) or (
                completion.get("accepted_state_digest")
                != accepted.get("accepted_state_digest")
                or selection.get("action_selection_digest")
                != completion.get("action_selection_digest")
                or preselection.get("preselection_digest")
                != completion.get("preselection_digest")
                or _timestamp(
                    completion.get("completed_at"), "V31_COMPLETION_TIME_INVALID"
                )
                < _timestamp(
                    accepted.get("selected_at"), "V31_SELECTION_TIME_INVALID"
                )
            ):
                raise V31ResearchStoreError("V31_COMPLETION_CHAIN_BINDING_INVALID")

    def _verify_event_artifact(
        self, event: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        relative_ref = str(event.get("artifact_ref") or "")
        target = self._safe_path(relative_ref)
        if not target.is_file():
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_MISSING")
        physical = hashlib.sha256(target.read_bytes()).hexdigest()
        if physical != event.get("artifact_physical_sha256"):
            raise V31ResearchStoreError("V31_EVENT_ARTIFACT_PHYSICAL_DRIFT")
        document = load_json_strict(target)
        semantic = str(event.get("artifact_semantic_digest") or "")
        self._verify_contract_document(
            event_type=str(event.get("event_type") or ""),
            document=document,
            run_id=str(event.get("run_id") or ""),
            cycle_index=int(event.get("cycle_index") or 0),
            semantic_digest=semantic,
        )
        return document

    def read_events(
        self, *, run_id: str, cycle_index: int
    ) -> Sequence[Mapping[str, Any]]:
        root = self._event_root(cycle_index)
        if not root.exists():
            return ()
        events: list[Mapping[str, Any]] = []
        documents: list[Mapping[str, Any]] = []
        previous = ZERO_DIGEST
        paths = sorted(root.glob("*.json"))
        for sequence, path in enumerate(paths):
            event = load_json_strict(path)
            try:
                verify_self_digest(event, "event_digest")
            except ValueError as exc:
                raise V31ResearchStoreError("V31_EVENT_DIGEST_INVALID") from exc
            if (
                sequence >= len(_EVENT_ORDER)
                or event.get("schema_id") != "theory_paper_v31_cycle_event"
                or event.get("schema_version") != "1.0.0"
                or event.get("run_id") != run_id
                or event.get("cycle_index") != cycle_index
                or event.get("sequence") != sequence
                or event.get("event_type") != _EVENT_ORDER[sequence]
                or event.get("previous_event_digest") != previous
                or path.name != f"{sequence:04d}-{_EVENT_ORDER[sequence]}.json"
                or event.get("external_execution_authority")
                != "NONE_LOCAL_SIMULATION"
                or event.get("executable") is not False
            ):
                raise V31ResearchStoreError("V31_EVENT_CHAIN_BROKEN")
            if events and _timestamp(event["recorded_at"], "V31_EVENT_TIME_INVALID") < _timestamp(
                events[-1]["recorded_at"], "V31_EVENT_TIME_INVALID"
            ):
                raise V31ResearchStoreError("V31_EVENT_TIME_INVALID")
            document = self._verify_event_artifact(event)
            if _timestamp(
                event.get("recorded_at"), "V31_EVENT_TIME_INVALID"
            ) < _timestamp(
                document.get(_ARTIFACT_TIME_FIELD[str(event["event_type"])]),
                "V31_EVENT_ARTIFACT_TIME_INVALID",
            ):
                raise V31ResearchStoreError("V31_EVENT_PRECEDES_ARTIFACT")
            documents.append(document)
            self._verify_cross_stage_documents(
                run_id=run_id,
                cycle_index=cycle_index,
                documents=documents,
            )
            previous = str(event["event_digest"])
            events.append(event)
        return tuple(events)

    def append_event(
        self,
        *,
        run_id: str,
        cycle_index: int,
        event_type: str,
        artifact_binding: Mapping[str, str],
        recorded_at: str,
    ) -> Mapping[str, Any]:
        with self._exclusive_lock(f"events-{cycle_index:04d}"):
            checkpoint = self.load_checkpoint(run_id=run_id)
            if (
                checkpoint.get("status") != "CYCLE_IN_PROGRESS"
                or checkpoint.get("active_cycle_index") != cycle_index
            ):
                raise V31ResearchStoreError("V31_EVENT_CHECKPOINT_NOT_OPEN")
            events = self.read_events(run_id=run_id, cycle_index=cycle_index)
            if len(events) >= len(_EVENT_ORDER) or event_type != _EVENT_ORDER[len(events)]:
                raise V31ResearchStoreError("V31_EVENT_ORDER_INVALID")
            if set(artifact_binding) != {
                "relative_ref",
                "semantic_digest",
                "physical_sha256",
            }:
                raise V31ResearchStoreError("V31_EVENT_ARTIFACT_BINDING_INVALID")
            for name in ("semantic_digest", "physical_sha256"):
                if _HEX_64.fullmatch(str(artifact_binding.get(name) or "")) is None:
                    raise V31ResearchStoreError("V31_EVENT_ARTIFACT_BINDING_INVALID")
            _timestamp(recorded_at, "V31_EVENT_TIME_INVALID")
            target = self._safe_path(str(artifact_binding["relative_ref"]))
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != artifact_binding[
                "physical_sha256"
            ]:
                raise V31ResearchStoreError("V31_EVENT_ARTIFACT_BINDING_INVALID")
            loaded = load_json_strict(target)
            self._verify_contract_document(
                event_type=event_type,
                document=loaded,
                run_id=run_id,
                cycle_index=cycle_index,
                semantic_digest=str(artifact_binding["semantic_digest"]),
            )
            if _timestamp(recorded_at, "V31_EVENT_TIME_INVALID") < _timestamp(
                loaded.get(_ARTIFACT_TIME_FIELD[event_type]),
                "V31_EVENT_ARTIFACT_TIME_INVALID",
            ):
                raise V31ResearchStoreError("V31_EVENT_PRECEDES_ARTIFACT")
            existing_documents = [
                self._verify_event_artifact(event) for event in events
            ]
            self._verify_cross_stage_documents(
                run_id=run_id,
                cycle_index=cycle_index,
                documents=(*existing_documents, loaded),
            )
            sequence = len(events)
            event = self_digest(
                {
                    "schema_id": "theory_paper_v31_cycle_event",
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "sequence": sequence,
                    "event_type": event_type,
                    "artifact_ref": artifact_binding["relative_ref"],
                    "artifact_semantic_digest": artifact_binding["semantic_digest"],
                    "artifact_physical_sha256": artifact_binding["physical_sha256"],
                    "recorded_at": recorded_at,
                    "previous_event_digest": (
                        ZERO_DIGEST if not events else events[-1]["event_digest"]
                    ),
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "event_digest",
            )
            root = self._event_root(cycle_index)
            write_once_json(root / f"{sequence:04d}-{event_type}.json", event)
            return event


__all__ = ["LocalV31ResearchStore", "V31ResearchStoreError"]
