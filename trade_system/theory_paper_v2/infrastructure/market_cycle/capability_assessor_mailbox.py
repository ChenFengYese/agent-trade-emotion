"""Create-once transport for one real V3.3.2 capability assessor Worker.

The mailbox does not judge findings.  It binds the controller task to the
pre-outcome evidence basis and exposes the exact Agent-authored findings file
that the controller completion receipt attests.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...domain.market_cycle.capability_evaluation import (
    CAPABILITY_CRITERIA,
    FINDING_STATUSES,
)
from ...domain.market_cycle.paper_capability_evaluation import (
    ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS,
    PAPER_CAPABILITY_CRITERIA,
    PAPER_EVIDENCE_SOURCE_KINDS,
    PAPER_FINDING_STATUSES,
)
from ...v32_durable_json import write_once_json


REQUEST_SCHEMA_ID = "agent-trade-emotion.v332-capability-assessor-request"
RESULT_SCHEMA_ID = "agent-trade-emotion.v332-capability-assessor-findings"
OUTPUT_CONTRACT_SCHEMA_ID = (
    "agent-trade-emotion.v332-capability-assessor-findings-contract"
)
SCHEMA_VERSION = "1.0.0"
OUTPUT_CONTRACT_SCHEMA_VERSION = "1.2.0"
REQUEST_NAME = "capability-assessor-request.json"
RESULT_NAME = "capability-assessor-findings.json"
_MAX_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTENTION_STREAM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}$")
_REQUEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "packet",
        "packet_sha256",
        "packet_size_bytes",
    }
)
_PACKET_FIELDS = frozenset(
    {
        "cycle_id",
        "task_id",
        "capability_id",
        "policy_sha256",
        "subject_agent_id",
        "evidence_kind",
        "task_basis",
        "task_basis_sha256",
        "capability_task_path",
        "issued_at",
        "assessment_due_at",
        "time_budget_seconds",
        "theory_identity",
        "output_contract",
        "instructions",
    }
)
_RESULT_FIELD_ORDER = (
    "assessor_execution_ref",
    "capability_id",
    "completed_at",
    "cycle_id",
    "findings",
    "schema_id",
    "schema_version",
    "task_id",
    "task_sha256",
    "worker_id",
)
_RESULT_FIELDS = frozenset(_RESULT_FIELD_ORDER)
_FINDING_FIELD_ORDER = (
    "criterion_id",
    "evidence_spans",
    "rationale",
    "status",
)
_GENERAL_SPAN_FIELDS = ("end_byte", "start_byte", "utf8_sha256")
_PAPER_SPAN_FIELDS = (
    "cycle_id",
    "end_byte",
    "selected_utf8_sha256",
    "source_kind",
    "source_sha256",
    "start_byte",
)


class CapabilityAssessorMailboxError(RuntimeError):
    """The assessor request or result failed its exact transport contract."""


def _time(value: object, *, code: str) -> datetime:
    if type(value) is not str or not value:
        raise CapabilityAssessorMailboxError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityAssessorMailboxError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapabilityAssessorMailboxError(code)
    return parsed


class LocalCapabilityAssessorMailbox:
    """Own the assessor request/result paths inside the existing cycle root."""

    def __init__(self, runtime_root: Path | str) -> None:
        self._root = Path(runtime_root).absolute()
        self._cycles = self._root / "cycles"

    def _path(self, cycle_id: str, name: str) -> Path:
        if type(cycle_id) is not str or not cycle_id or "/" in cycle_id:
            raise CapabilityAssessorMailboxError("ASSESSOR_CYCLE_ID_INVALID")
        path = self._cycles / cycle_id / "transport" / name
        try:
            transport = path.parent.resolve(strict=True)
            transport.relative_to(self._cycles.resolve(strict=True))
            metadata = transport.lstat()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_TRANSPORT_PATH_INVALID"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise CapabilityAssessorMailboxError("ASSESSOR_TRANSPORT_PATH_INVALID")
        return path

    def request_path(self, cycle_id: str) -> Path:
        return self._path(cycle_id, REQUEST_NAME)

    def result_path(self, cycle_id: str) -> Path:
        return self._path(cycle_id, RESULT_NAME)

    def _attention_checkpoint_path(
        self, logical_agent_id: object, revision: object
    ) -> Path:
        if (
            type(logical_agent_id) is not str
            or _ATTENTION_STREAM_ID_RE.fullmatch(logical_agent_id) is None
            or type(revision) is not int
            or revision < 2
        ):
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_ATTENTION_CHECKPOINT_PATH_INVALID"
            )
        events_root = self._root / "attention" / "streams" / logical_agent_id / "events"
        path = events_root / f"{revision:08d}.json"
        try:
            resolved_root = events_root.resolve(strict=True)
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_root)
            metadata = path.lstat()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_ATTENTION_CHECKPOINT_PATH_INVALID"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_ATTENTION_CHECKPOINT_PATH_INVALID"
            )
        return resolved

    def output_contract(
        self,
        *,
        cycle_id: str,
        evidence_kind: str,
        capability_id: str,
        capability_task_path: str,
        task_basis: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Publish the complete companion findings contract to the assessor."""

        if evidence_kind == "GENERAL":
            criteria = CAPABILITY_CRITERIA.get(capability_id)
            statuses = FINDING_STATUSES
            span_fields = _GENERAL_SPAN_FIELDS
            source_kinds: tuple[str, ...] = ()
            span_semantics = (
                "HALF_OPEN_UTF8_BYTE_RANGE_IN_SEALED_AGENT_DECISION_TEXT"
            )
        elif evidence_kind == "PAPER":
            criteria = PAPER_CAPABILITY_CRITERIA.get(capability_id)
            statuses = PAPER_FINDING_STATUSES
            span_fields = _PAPER_SPAN_FIELDS
            source_kinds = (
                ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS
                if capability_id == "ATTENTION_SCHEDULING"
                else PAPER_EVIDENCE_SOURCE_KINDS
            )
            span_semantics = (
                "HALF_OPEN_UTF8_BYTE_RANGE_IN_EXACT_AGENT_OWNED_SOURCE"
            )
        else:
            criteria = None
            statuses = frozenset()
            span_fields = ()
            source_kinds = ()
            span_semantics = ""
        if criteria is None:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_OUTPUT_CONTRACT_CAPABILITY_INVALID"
            )
        if type(capability_task_path) is not str or not capability_task_path:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_OUTPUT_CONTRACT_TASK_PATH_INVALID"
            )
        if not isinstance(task_basis, Mapping):
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_OUTPUT_CONTRACT_TASK_BASIS_INVALID"
            )
        cycle_ids = [cycle_id]
        points_by_cycle: dict[str, Mapping[str, Any]] = {}
        if evidence_kind == "PAPER":
            points = task_basis.get("decision_points")
            if not isinstance(points, list) or not points:
                raise CapabilityAssessorMailboxError(
                    "ASSESSOR_OUTPUT_CONTRACT_TASK_BASIS_INVALID"
                )
            cycle_ids = []
            for point in points:
                if not isinstance(point, Mapping):
                    raise CapabilityAssessorMailboxError(
                        "ASSESSOR_OUTPUT_CONTRACT_TASK_BASIS_INVALID"
                    )
                point_cycle = point.get("cycle_id")
                if type(point_cycle) is not str or not point_cycle:
                    raise CapabilityAssessorMailboxError(
                        "ASSESSOR_OUTPUT_CONTRACT_TASK_BASIS_INVALID"
                    )
                if point_cycle not in cycle_ids:
                    cycle_ids.append(point_cycle)
                points_by_cycle[point_cycle] = point
        evidence_sources: list[dict[str, Any]] = []
        for source_cycle in cycle_ids:
            transport = self._path(source_cycle, REQUEST_NAME).parent
            if "DECISION_TEXT" in ({"DECISION_TEXT"} | set(source_kinds)):
                evidence_sources.append(
                    {
                        "cycle_id": source_cycle,
                        "source_kind": "DECISION_TEXT",
                        "path": str(
                            (
                                self._cycles
                                / source_cycle
                                / "artifacts"
                                / "HypothesisRecord.json"
                            ).absolute()
                        ),
                        "json_pointer": "/agent_decision_text",
                        "bytes": "UTF8_ENCODING_OF_JSON_STRING_VALUE",
                    }
                )
            if "EXECUTION_INTENT" in source_kinds:
                evidence_sources.append(
                    {
                        "cycle_id": source_cycle,
                        "source_kind": "EXECUTION_INTENT",
                        "path": str(
                            (transport / "paper-execution-intent.json").absolute()
                        ),
                        "json_pointer": "",
                        "bytes": "CANONICAL_DOCUMENT_BYTES_WITHOUT_TRAILING_LF",
                    }
                )
            if "ATTENTION_REQUEST" in source_kinds:
                point = points_by_cycle[source_cycle]
                checkpoint_revision = point.get("attention_checkpoint_revision")
                checkpoint_event_sha256 = point.get(
                    "attention_checkpoint_event_sha256"
                )
                checkpoint_document_sha256 = point.get(
                    "attention_checkpoint_document_sha256"
                )
                stream_head_revision = point.get("attention_stream_head_revision")
                stream_head_event_sha256 = point.get(
                    "attention_stream_head_event_sha256"
                )
                stream_head_document_sha256 = point.get(
                    "attention_stream_head_document_sha256"
                )
                attention_sha256 = point.get("attention_sha256")
                if (
                    type(checkpoint_revision) is not int
                    or checkpoint_revision < 2
                    or stream_head_revision != checkpoint_revision
                    or stream_head_event_sha256 != checkpoint_event_sha256
                    or any(
                        type(value) is not str
                        or _SHA256_RE.fullmatch(value) is None
                        for value in (
                            checkpoint_event_sha256,
                            checkpoint_document_sha256,
                            stream_head_event_sha256,
                            stream_head_document_sha256,
                            attention_sha256,
                        )
                    )
                ):
                    raise CapabilityAssessorMailboxError(
                        "ASSESSOR_OUTPUT_CONTRACT_TASK_BASIS_INVALID"
                    )
                checkpoint_path = self._attention_checkpoint_path(
                    point.get("logical_agent_id"), checkpoint_revision
                )
                evidence_sources.append(
                    {
                        "cycle_id": source_cycle,
                        "source_kind": "ATTENTION_REQUEST",
                        "path": str(checkpoint_path),
                        "json_pointer": "/payload/request",
                        "bytes": "CANONICAL_JSON_VALUE_BYTES",
                        "source_sha256": attention_sha256,
                        "checkpoint_document_sha256": (
                            checkpoint_document_sha256
                        ),
                        "checkpoint_event_sha256": checkpoint_event_sha256,
                        "checkpoint_revision": checkpoint_revision,
                        "stream_head_document_sha256": (
                            stream_head_document_sha256
                        ),
                        "stream_head_event_sha256": stream_head_event_sha256,
                        "stream_head_revision": stream_head_revision,
                    }
                )
        return {
            "schema_id": OUTPUT_CONTRACT_SCHEMA_ID,
            "schema_version": OUTPUT_CONTRACT_SCHEMA_VERSION,
            "canonical_encoding": (
                "RFC8259_CANONICAL_COMPACT_UTF8_SORTED_KEYS_PLUS_ONE_NEWLINE"
            ),
            "output_path": str(self.result_path(cycle_id).absolute()),
            "exact_fields": list(_RESULT_FIELD_ORDER),
            "fixed_values": {
                "schema_id": RESULT_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "cycle_id": cycle_id,
                "worker_id": "capability-assessor-v1",
                "capability_id": capability_id,
            },
            "dynamic_values": {
                "task_id": f"{capability_task_path}#/document/task_id",
                "task_sha256": f"{capability_task_path}#/document_sha256",
                "assessor_execution_ref": (
                    f"{capability_task_path}#/document/assessor_id"
                ),
                "completed_at": "EXACTLY_EQUAL_TO_WORKER_RESULT.completed_at",
            },
            "evidence_sources": evidence_sources,
            "findings": {
                "cardinality": len(criteria),
                "order": "EXACT",
                "criterion_ids": list(criteria),
                "exact_fields": list(_FINDING_FIELD_ORDER),
                "allowed_statuses": sorted(statuses),
                "rationale": "NON_EMPTY_READABLE_UTF8_MAX_16384_BYTES",
                "demonstrated_requires_nonempty_evidence_spans": True,
                "evidence_span_exact_fields": list(span_fields),
                "evidence_span_semantics": span_semantics,
                "allowed_source_kinds": list(source_kinds),
                "selected_bytes_sha256_must_match": True,
            },
            "global_constraints": [
                "EXACT_FIELDS_LISTS_ARE_CANONICAL_WIRE_ORDER_FOR_DECLARED_OBJECTS",
                "RECURSIVELY_SORT_ALL_OBJECT_KEYS_BY_UTF16_CODE_UNITS",
                "SERIALIZE_COMPACT_UTF8_AND_APPEND_EXACTLY_ONE_LF",
                "BUILD_COMPLETE_DOCUMENT_BEFORE_CREATE_ONCE_WRITE",
            ],
        }

    def _validate_packet(self, packet: Mapping[str, Any]) -> None:
        if (
            not isinstance(packet, Mapping)
            or frozenset(packet) != _PACKET_FIELDS
            or packet.get("evidence_kind") not in {"GENERAL", "PAPER"}
            or not isinstance(packet.get("task_basis"), Mapping)
            or packet.get("task_basis_sha256")
            != canonical_digest(packet["task_basis"])
            or not isinstance(packet.get("theory_identity"), Mapping)
            or type(packet.get("time_budget_seconds")) is not int
            or not (0 < packet["time_budget_seconds"] <= 86_400)
            or type(packet.get("capability_task_path")) is not str
            or not packet["capability_task_path"]
            or type(packet.get("subject_agent_id")) is not str
            or not packet["subject_agent_id"]
            or not isinstance(packet.get("output_contract"), Mapping)
            or type(packet.get("instructions")) is not str
            or not packet["instructions"].strip()
            or type(packet.get("policy_sha256")) is not str
            or _SHA256_RE.fullmatch(packet["policy_sha256"]) is None
        ):
            raise CapabilityAssessorMailboxError("ASSESSOR_REQUEST_PACKET_INVALID")
        try:
            expected_output = self.output_contract(
                cycle_id=str(packet["cycle_id"]),
                evidence_kind=str(packet["evidence_kind"]),
                capability_id=str(packet["capability_id"]),
                capability_task_path=str(packet["capability_task_path"]),
                task_basis=packet["task_basis"],
            )
        except (KeyError, CapabilityAssessorMailboxError) as exc:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_REQUEST_PACKET_INVALID"
            ) from exc
        if dict(packet["output_contract"]) != expected_output:
            raise CapabilityAssessorMailboxError("ASSESSOR_REQUEST_PACKET_INVALID")
        issued = _time(packet.get("issued_at"), code="ASSESSOR_REQUEST_TIME_INVALID")
        due = _time(
            packet.get("assessment_due_at"), code="ASSESSOR_REQUEST_TIME_INVALID"
        )
        if due <= issued:
            raise CapabilityAssessorMailboxError("ASSESSOR_REQUEST_TIME_INVALID")

    def issue(self, *, cycle_id: str, packet: Mapping[str, Any]) -> Path:
        self._validate_packet(packet)
        if packet.get("cycle_id") != cycle_id:
            raise CapabilityAssessorMailboxError("ASSESSOR_REQUEST_CYCLE_MISMATCH")
        packet_document = dict(packet)
        packet_raw = canonical_bytes(packet_document)
        document = {
            "schema_id": REQUEST_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "cycle_id": cycle_id,
            "packet": packet_document,
            "packet_sha256": canonical_digest(packet_document),
            "packet_size_bytes": len(packet_raw),
        }
        try:
            status = write_once_json(self.request_path(cycle_id), document)
        except (OSError, CanonicalContractError) as exc:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_REQUEST_WRITE_ONCE_CONFLICT"
            ) from exc
        if status not in {"CREATED", "EXISTING_IDENTICAL"}:
            raise CapabilityAssessorMailboxError(
                "ASSESSOR_REQUEST_WRITE_ONCE_CONFLICT"
            )
        self.load_request(cycle_id)
        return self.request_path(cycle_id).resolve(strict=True)

    @staticmethod
    def _read(path: Path, *, code: str) -> tuple[Mapping[str, Any], bytes]:
        try:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size < 2
                or metadata.st_size > _MAX_BYTES
            ):
                raise OSError
            raw = path.read_bytes()
            value = loads_json_strict(raw)
        except (FileNotFoundError, OSError, CanonicalContractError) as exc:
            raise CapabilityAssessorMailboxError(code) from exc
        if not isinstance(value, Mapping) or canonical_bytes(value) + b"\n" != raw:
            raise CapabilityAssessorMailboxError(code)
        return value, raw

    def load_request(self, cycle_id: str) -> Mapping[str, Any]:
        value, _ = self._read(
            self.request_path(cycle_id), code="ASSESSOR_REQUEST_INVALID"
        )
        packet = value.get("packet")
        if (
            frozenset(value) != _REQUEST_FIELDS
            or value.get("schema_id") != REQUEST_SCHEMA_ID
            or value.get("schema_version") != SCHEMA_VERSION
            or value.get("cycle_id") != cycle_id
            or not isinstance(packet, Mapping)
            or value.get("packet_sha256") != canonical_digest(packet)
            or value.get("packet_size_bytes") != len(canonical_bytes(packet))
        ):
            raise CapabilityAssessorMailboxError("ASSESSOR_REQUEST_INVALID")
        self._validate_packet(packet)
        return value

    def load_result(self, cycle_id: str) -> tuple[Mapping[str, Any], bytes]:
        value, raw = self._read(
            self.result_path(cycle_id), code="ASSESSOR_RESULT_INVALID"
        )
        if (
            frozenset(value) != _RESULT_FIELDS
            or value.get("schema_id") != RESULT_SCHEMA_ID
            or value.get("schema_version") != SCHEMA_VERSION
            or value.get("cycle_id") != cycle_id
            or value.get("worker_id") != "capability-assessor-v1"
            or type(value.get("findings")) is not list
            or not value["findings"]
            or not all(isinstance(item, Mapping) for item in value["findings"])
            or type(value.get("task_sha256")) is not str
            or _SHA256_RE.fullmatch(value["task_sha256"]) is None
            or type(value.get("assessor_execution_ref")) is not str
            or not value["assessor_execution_ref"]
        ):
            raise CapabilityAssessorMailboxError("ASSESSOR_RESULT_INVALID")
        _time(value.get("completed_at"), code="ASSESSOR_RESULT_INVALID")
        return value, raw


__all__ = [
    "CapabilityAssessorMailboxError",
    "LocalCapabilityAssessorMailbox",
    "OUTPUT_CONTRACT_SCHEMA_ID",
    "OUTPUT_CONTRACT_SCHEMA_VERSION",
    "REQUEST_NAME",
    "REQUEST_SCHEMA_ID",
    "RESULT_NAME",
    "RESULT_SCHEMA_ID",
    "SCHEMA_VERSION",
]
