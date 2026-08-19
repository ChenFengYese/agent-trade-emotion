"""Two-stage, write-once verbatim Agent transport for market cycles.

The mailbox owns only transport sidecars.  The Agent supplies readable UTF-8
text; the system constructs and binds the request and delivery envelopes.  No
business vocabulary, proposal schema, action selection, or position policy is
validated here.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping

from ...application.market_cycle.ports import (
    AgentAnalysisPending,
    AgentDecision,
    AgentDecisionDeadlineExpired,
    AgentPacket,
    AgentReview,
    AgentReviewDeadlineExpired,
    AgentReviewPacket,
    AgentReviewPending,
)
from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    MarketCycleContractError,
    Outcome,
    validate_snapshot_bound_memory_context,
)
from ...domain.market_cycle.evidence import calculate_multitimeframe_context
from ...v32_durable_json import write_once_json
from .goal_identity import CodexGoalIdentityError, current_codex_goal_identity


_SAFE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_REQUEST_SCHEMA = "agent_trade_emotion_market_cycle_agent_decision_request"
_DELIVERY_SCHEMA = "agent_trade_emotion_market_cycle_agent_decision_delivery"
_REVIEW_REQUEST_SCHEMA = "agent_trade_emotion_market_cycle_agent_review_request"
_REVIEW_DELIVERY_SCHEMA = "agent_trade_emotion_market_cycle_agent_review_delivery"
_SCHEMA_VERSION = "1.0.0"
_GOAL_DELIVERY_SCHEMA_VERSION = "1.1.0"
_MAX_DECISION_PACKET_BYTES = 8 * 1024 * 1024
_MAX_REVIEW_PACKET_BYTES = 8 * 1024 * 1024
_MAX_DECISION_BYTES = 256 * 1024
_MAX_REVIEW_BYTES = 256 * 1024
_REVIEW_TIME_BUDGET_SECONDS = 600
_DEFAULT_MEDIA_TYPE = "application/octet-stream"
_MAX_MEDIA_TYPE_CHARACTERS = 255
_DELIVERY_RELATIVE_PATH = Path("transport/agent-delivery.json")
_REVIEW_REQUEST_RELATIVE_PATH = Path("transport/agent-review-request.json")
_REVIEW_DELIVERY_RELATIVE_PATH = Path("transport/agent-review-delivery.json")
_PHYSICAL_GOAL_ID = re.compile(
    r"codex-thread:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
_DECISION_DELIVERY_BASE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "request_sha256",
        "theory_identity",
        "delivered_at",
        "media_type",
        "encoding",
        "decision_size_bytes",
        "decision_sha256",
        "decision_text",
    }
)

_DECISION_INSTRUCTIONS = (
    "Use only admitted point-in-time facts and keep unavailable facts UNKNOWN.",
    "Return one readable UTF-8 decision in JSON, Markdown, plain text, or any mixed structure you choose.",
    "The published transport capacity for the decision body is 262144 UTF-8 bytes.",
    "You own hypotheses, their updates, the final non-executable reference action, and any entry, stop, targets, or position-management text.",
    "Treat lawful_actions as reference navigation rather than a closed decision vocabulary; use OTHER_INFORMATION_ACTION for a lawful informational action not enumerated there.",
    "The system does not choose, normalize, or execute your market decision.",
    "The system will construct the transport envelope and will not rewrite your decision text.",
    "No account facts, credentials, orders, funds, paper, testnet, or live execution are authorized.",
)
_LOCAL_PAPER_DECISION_INSTRUCTIONS = (
    *_DECISION_INSTRUCTIONS[:-1],
    "This run authorizes only a separately supplied, digest-bound local paper account context and Agent-authored paper execution intent; this market packet alone cannot create a paper command.",
    "Before proposing a paper-executable action, read packet.paper_context.paper_action_space: standalone MARKET may be available, while a protected flat-entry bracket currently requires a bounded LIMIT entry; unsupported combinations remain lawful reference ideas but will be blocked rather than rewritten.",
    "No private account facts, credentials, external orders, funds, testnet, or live execution are authorized.",
)
_REVIEW_INSTRUCTIONS = (
    "Review the exact original InputSnapshot, AgentDecision, HypothesisRecord, BehaviorPlan, and system-recorded Outcome using the complete verified theory context.",
    "Return one readable UTF-8 review in JSON, Markdown, plain text, or any mixed structure you choose.",
    "The published transport capacity for the review body is 262144 UTF-8 bytes.",
    "You alone own market interpretation, hypothesis updates, learning conclusions, and any future reference-action implications.",
    "The system will preserve your review verbatim and will not infer, rewrite, or write back theory conclusions.",
    "When packet.paper_review_context is present, use its exact local-paper intent, attention, ledger, order/fill, valuation, and cost facts; they are modeled evidence rather than actual execution.",
    "No account facts, credentials, orders, funds, paper, testnet, or live execution are authorized.",
)
_LOCAL_PAPER_REVIEW_INSTRUCTIONS = (
    *_REVIEW_INSTRUCTIONS[:-1],
    "Review any separately supplied, digest-bound local paper facts as paper evidence only; do not describe paper fill as actual execution.",
    "No private account facts, credentials, external orders, funds, testnet, or live execution are authorized.",
)
_AGENT_PACKET_FIELDS = frozenset(field.name for field in fields(AgentPacket))
_AGENT_PACKET_BASE_FIELDS = _AGENT_PACKET_FIELDS - {"paper_context"}
_AGENT_REVIEW_PACKET_FIELDS = frozenset(
    field.name for field in fields(AgentReviewPacket)
)
_AGENT_REVIEW_PACKET_BASE_FIELDS = _AGENT_REVIEW_PACKET_FIELDS - {
    "paper_review_context"
}


class MarketCycleAgentMailboxError(ValueError):
    """The bounded mailbox contract was violated."""


class LocalMarketCycleAgentMailbox:
    """Transport one Agent decision and one post-Outcome review per cycle."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], str],
        local_paper_authorized: bool = False,
        decision_context: object | None = None,
    ) -> None:
        if type(local_paper_authorized) is not bool:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_LOCAL_PAPER_AUTHORITY_INVALID"
            )
        self._root = Path(root)
        self._clock = clock
        if decision_context is not None and not callable(
            getattr(decision_context, "context", None)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_DECISION_CONTEXT_PORT_INVALID"
            )
        if decision_context is not None and not callable(
            getattr(decision_context, "verifies_context", None)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_DECISION_CONTEXT_PORT_INVALID"
            )
        if local_paper_authorized and decision_context is None:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_LOCAL_PAPER_CONTEXT_REQUIRED"
            )
        self._decision_context = decision_context
        self._decision_instructions = (
            _LOCAL_PAPER_DECISION_INSTRUCTIONS
            if local_paper_authorized
            else _DECISION_INSTRUCTIONS
        )
        self._review_instructions = (
            _LOCAL_PAPER_REVIEW_INSTRUCTIONS
            if local_paper_authorized
            else _REVIEW_INSTRUCTIONS
        )

    @staticmethod
    def _cycle(value: str) -> str:
        if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_ID_INVALID")
        return value

    def _request_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / "transport" / "agent-request.json"

    def _delivery_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _DELIVERY_RELATIVE_PATH

    def _review_request_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _REVIEW_REQUEST_RELATIVE_PATH

    def _review_delivery_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _REVIEW_DELIVERY_RELATIVE_PATH

    @staticmethod
    def _delivery_goal_identity(
        delivery: Mapping[str, Any],
        *,
        base_fields: frozenset[str],
        error_code: str,
    ) -> str | None:
        """Validate the exact Worker or Goal delivery envelope shape."""

        fields = frozenset(delivery)
        if fields == base_fields:
            if delivery.get("schema_version") != _SCHEMA_VERSION:
                raise MarketCycleAgentMailboxError(error_code)
            return None
        if fields != base_fields | {"physical_goal_id"}:
            raise MarketCycleAgentMailboxError(error_code)
        physical_goal_id = delivery.get("physical_goal_id")
        if (
            delivery.get("schema_version") != _GOAL_DELIVERY_SCHEMA_VERSION
            or not isinstance(physical_goal_id, str)
            or _PHYSICAL_GOAL_ID.fullmatch(physical_goal_id) is None
        ):
            raise MarketCycleAgentMailboxError(error_code)
        return physical_goal_id

    @staticmethod
    def _current_goal_identity() -> str:
        try:
            return current_codex_goal_identity()
        except CodexGoalIdentityError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_GOAL_IDENTITY_REQUIRED"
            ) from exc

    def delivery_present(self, cycle_id: str) -> bool:
        """Fail closed when any decision-delivery path entry already exists."""

        return self._path_present(self._delivery_path(cycle_id))

    def review_delivery_present(self, cycle_id: str) -> bool:
        """Fail closed when any review-delivery path entry already exists."""

        return self._path_present(self._review_delivery_path(cycle_id))

    @staticmethod
    def _timestamp(value: object, *, error_code: str) -> datetime:
        if not isinstance(value, str) or not value:
            raise MarketCycleAgentMailboxError(error_code)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MarketCycleAgentMailboxError(error_code) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise MarketCycleAgentMailboxError(error_code)
        return parsed

    @classmethod
    def _outcome_due_at(cls, snapshot: InputSnapshot) -> datetime:
        return cls._timestamp(
            snapshot.decision_at,
            error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
        ) + timedelta(seconds=snapshot.outcome_horizon_seconds)

    @staticmethod
    def _path_present(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DOCUMENT_PRESENCE_UNAVAILABLE"
            ) from exc
        return True

    @staticmethod
    def _read(path: Path) -> tuple[dict[str, Any], bytes]:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_DOCUMENT_UNSAFE:{path.name}"
            )
        try:
            raw = path.read_bytes()
            value = loads_json_strict(raw)
            if not isinstance(value, Mapping):
                raise CanonicalContractError("DOCUMENT_NOT_OBJECT")
            if canonical_bytes(value) + b"\n" != raw:
                raise CanonicalContractError("DOCUMENT_NOT_CANONICAL")
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_DOCUMENT_INVALID:{path.name}"
            ) from exc
        return dict(value), raw

    def _request_snapshot(
        self, request: Mapping[str, Any], *, cycle_id: str
    ) -> InputSnapshot:
        if (
            set(request)
            != {
                "schema_id",
                "schema_version",
                "cycle_id",
                "request_id",
                "packet_sha256",
                "packet_size_bytes",
                "packet",
                "instructions",
            }
            or request.get("schema_id") != _REQUEST_SCHEMA
            or request.get("schema_version") != _SCHEMA_VERSION
            or request.get("cycle_id") != cycle_id
            or request.get("instructions") != list(self._decision_instructions)
        ):
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_AGENT_REQUEST_INVALID")
        packet = request.get("packet")
        expected_packet_fields = (
            _AGENT_PACKET_FIELDS
            if self._decision_context is not None
            else _AGENT_PACKET_BASE_FIELDS
        )
        if (
            not isinstance(packet, Mapping)
            or frozenset(packet) != expected_packet_fields
        ):
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_AGENT_REQUEST_INVALID")
        try:
            packet_bytes = canonical_bytes(packet)
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_INVALID"
            ) from exc
        if (
            len(packet_bytes) > _MAX_DECISION_PACKET_BYTES
            or request.get("packet_sha256") != hashlib.sha256(packet_bytes).hexdigest()
            or request.get("packet_size_bytes") != len(packet_bytes)
            or packet.get("cycle_id") != cycle_id
            or packet.get("request_id") != request.get("request_id")
            or type(packet.get("token_budget")) is not int
            or packet["token_budget"] <= 0
            or type(packet.get("time_budget_seconds")) is not int
            or packet["time_budget_seconds"] <= 0
        ):
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_AGENT_REQUEST_INVALID")
        theory_fragments = packet.get("theory_fragments")
        if not isinstance(theory_fragments, Mapping) or not theory_fragments or not all(
            isinstance(name, str)
            and bool(name)
            and isinstance(content, str)
            and bool(content.strip())
            for name, content in theory_fragments.items()
        ):
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_AGENT_REQUEST_INVALID")
        try:
            snapshot = InputSnapshot.from_dict(packet["input_snapshot"])
        except (KeyError, TypeError, MarketCycleContractError) as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_INVALID"
            ) from exc
        snapshot_ref = self._artifact_reference(
            packet.get("input_snapshot_ref"),
            snapshot,
            artifact_type="InputSnapshot",
            artifact_id=snapshot.snapshot_id,
            error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
        )
        self._validate_auxiliary_context(
            packet,
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
            include_paper_context=self._decision_context is not None,
        )
        if (
            snapshot.cycle_id != cycle_id
            or snapshot.request_id != request.get("request_id")
            or packet.get("theory_identity") != snapshot.theory_identity.to_dict()
            or packet.get("lawful_actions") != list(snapshot.lawful_actions)
            or not isinstance(packet.get("memory_context"), Mapping)
            or not isinstance(packet.get("deterministic_calculations"), Mapping)
            or packet.get("decision_deadline_at") != snapshot.outcome_due_at
            or packet["time_budget_seconds"]
            > int(
                (
                    self._outcome_due_at(snapshot)
                    - self._timestamp(
                        snapshot.sealed_at,
                        error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
                    )
                ).total_seconds()
            )
        ):
            raise MarketCycleAgentMailboxError("MARKET_CYCLE_AGENT_REQUEST_INVALID")
        return snapshot

    @staticmethod
    def _verbatim_text(
        raw: bytes, *, kind: str, maximum_bytes: int
    ) -> tuple[str, int, str]:
        if type(raw) is not bytes:
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_{kind}_BYTES_INVALID"
            )
        size_bytes = len(raw)
        if size_bytes > maximum_bytes:
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_{kind}_TRANSPORT_CAPACITY_EXCEEDED"
            )
        if size_bytes < 1:
            raise MarketCycleAgentMailboxError(f"MARKET_CYCLE_AGENT_{kind}_BLANK")
        try:
            value = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_{kind}_UTF8_INVALID"
            ) from exc
        if "\x00" in value:
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_{kind}_NUL_FORBIDDEN"
            )
        if not value.strip():
            raise MarketCycleAgentMailboxError(
                f"MARKET_CYCLE_AGENT_{kind}_BLANK"
            )
        return value, size_bytes, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _media_type_hint(value: object) -> str:
        """Return bounded transport metadata without making it an admission gate."""

        if not isinstance(value, str):
            return _DEFAULT_MEDIA_TYPE
        hint = value.strip()
        if (
            not hint
            or len(hint) > _MAX_MEDIA_TYPE_CHARACTERS
            or any(ord(character) < 32 or ord(character) > 126 for character in hint)
        ):
            return _DEFAULT_MEDIA_TYPE
        return hint

    @classmethod
    def _decision_text(cls, raw: bytes) -> tuple[str, int, str]:
        return cls._verbatim_text(
            raw, kind="DECISION", maximum_bytes=_MAX_DECISION_BYTES
        )

    @classmethod
    def _review_text(cls, raw: bytes) -> tuple[str, int, str]:
        return cls._verbatim_text(raw, kind="REVIEW", maximum_bytes=_MAX_REVIEW_BYTES)

    def _request_document(self, packet: AgentPacket) -> dict[str, Any]:
        packet_value = packet.to_dict()
        packet_bytes = canonical_bytes(packet_value)
        packet_size = len(packet_bytes)
        if packet_size > _MAX_DECISION_PACKET_BYTES:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_TRANSPORT_CAPACITY_EXCEEDED"
            )
        return {
            "schema_id": _REQUEST_SCHEMA,
            "schema_version": _SCHEMA_VERSION,
            "cycle_id": packet.cycle_id,
            "request_id": packet.request_id,
            "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
            "packet_size_bytes": packet_size,
            "packet": packet_value,
            "instructions": list(self._decision_instructions),
        }

    @staticmethod
    def _artifact_reference(
        value: object,
        artifact: object,
        *,
        artifact_type: str,
        artifact_id: str,
        error_code: str = "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
    ) -> ArtifactRef:
        try:
            if not isinstance(value, Mapping):
                raise MarketCycleContractError("artifact reference must be an object")
            reference = ArtifactRef.from_dict(value)
            to_dict = getattr(artifact, "to_dict")
            payload = canonical_bytes(to_dict())
        except (
            AttributeError,
            CanonicalContractError,
            KeyError,
            TypeError,
            MarketCycleContractError,
        ) as exc:
            raise MarketCycleAgentMailboxError(error_code) from exc
        if (
            reference.artifact_type != artifact_type
            or reference.artifact_id != artifact_id
            or reference.path != f"artifacts/{artifact_type}.json"
            or reference.size_bytes != len(payload)
            or reference.sha256 != hashlib.sha256(payload).hexdigest()
        ):
            raise MarketCycleAgentMailboxError(error_code)
        return reference

    def _validate_auxiliary_context(
        self,
        packet: Mapping[str, Any],
        *,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        error_code: str,
        include_paper_context: bool = False,
    ) -> None:
        """Rebuild non-authoritative inputs to detect a re-signed corrupt sidecar."""

        try:
            supplied_memory = packet.get("memory_context")
            if not isinstance(supplied_memory, Mapping):
                raise MarketCycleContractError("memory_context must be an object")
            expected_memory = validate_snapshot_bound_memory_context(
                snapshot, supplied_memory
            )
            expected_calculations = calculate_multitimeframe_context(
                snapshot, snapshot_ref
            ).to_dict()
            supplied_paper_context = packet.get("paper_context")
            paper_context_valid = (
                True
                if not include_paper_context
                else self._decision_context is not None
                and isinstance(supplied_paper_context, Mapping)
                and self._decision_context.verifies_context(
                    snapshot, snapshot_ref, supplied_paper_context
                )
            )
        except (CanonicalContractError, TypeError, ValueError) as exc:
            raise MarketCycleAgentMailboxError(error_code) from exc
        if (
            supplied_memory != expected_memory
            or packet.get("deterministic_calculations") != expected_calculations
            or not paper_context_valid
        ):
            raise MarketCycleAgentMailboxError(error_code)

    def _review_request_document(
        self, packet: AgentReviewPacket, *, review_requested_at: str
    ) -> dict[str, Any]:
        requested = self._timestamp(
            review_requested_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        packet_value = {
            **packet.to_dict(),
            "review_requested_at": review_requested_at,
            "review_due_at": (
                requested + timedelta(seconds=_REVIEW_TIME_BUDGET_SECONDS)
            ).isoformat(),
        }
        packet_bytes = canonical_bytes(packet_value)
        packet_size = len(packet_bytes)
        if packet_size > _MAX_REVIEW_PACKET_BYTES:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_TRANSPORT_CAPACITY_EXCEEDED"
            )
        return {
            "schema_id": _REVIEW_REQUEST_SCHEMA,
            "schema_version": _SCHEMA_VERSION,
            "cycle_id": packet.cycle_id,
            "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
            "packet_size_bytes": packet_size,
            "packet": packet_value,
            "instructions": list(self._review_instructions),
        }

    def _review_context(
        self, request: Mapping[str, Any], *, cycle_id: str
    ) -> tuple[BehaviorPlan, ArtifactRef, Outcome, ArtifactRef, datetime]:
        if (
            set(request)
            != {
                "schema_id",
                "schema_version",
                "cycle_id",
                "packet_sha256",
                "packet_size_bytes",
                "packet",
                "instructions",
            }
            or request.get("schema_id") != _REVIEW_REQUEST_SCHEMA
            or request.get("schema_version") != _SCHEMA_VERSION
            or request.get("cycle_id") != cycle_id
            or request.get("instructions") != list(self._review_instructions)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        packet = request.get("packet")
        expected_packet_fields = (
            _AGENT_REVIEW_PACKET_FIELDS
            if self._decision_context is not None
            else _AGENT_REVIEW_PACKET_BASE_FIELDS
        )
        if (
            not isinstance(packet, Mapping)
            or frozenset(packet)
            != expected_packet_fields | {"review_requested_at", "review_due_at"}
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        try:
            packet_bytes = canonical_bytes(packet)
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            ) from exc
        paper_review_context = packet.get("paper_review_context")
        if self._decision_context is None:
            if "paper_review_context" in packet:
                raise MarketCycleAgentMailboxError(
                    "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
                )
        else:
            snapshot_document = packet.get("input_snapshot")
            snapshot_ref_document = packet.get("input_snapshot_ref")
            outcome_document = packet.get("outcome")
            verifier = getattr(
                self._decision_context, "verifies_review_context", None
            )
            if (
                not isinstance(paper_review_context, Mapping)
                or not isinstance(snapshot_document, Mapping)
                or not isinstance(snapshot_ref_document, Mapping)
                or not isinstance(outcome_document, Mapping)
                or not callable(verifier)
                or not verifier(
                    InputSnapshot.from_dict(snapshot_document),
                    ArtifactRef.from_dict(snapshot_ref_document),
                    paper_review_context,
                    review_cutoff_at=str(outcome_document.get("sealed_at")),
                )
            ):
                raise MarketCycleAgentMailboxError(
                    "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
                )
        if (
            len(packet_bytes) > _MAX_REVIEW_PACKET_BYTES
            or request.get("packet_sha256") != hashlib.sha256(packet_bytes).hexdigest()
            or request.get("packet_size_bytes") != len(packet_bytes)
            or packet.get("cycle_id") != cycle_id
            or type(packet.get("token_budget")) is not int
            or packet["token_budget"] <= 0
            or packet.get("time_budget_seconds") != _REVIEW_TIME_BUDGET_SECONDS
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        theory_fragments = packet.get("theory_fragments")
        if not isinstance(theory_fragments, Mapping) or not theory_fragments or not all(
            isinstance(name, str)
            and bool(name)
            and isinstance(content, str)
            and bool(content.strip())
            for name, content in theory_fragments.items()
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        try:
            snapshot_value = packet["input_snapshot"]
            record_value = packet["hypothesis_record"]
            plan_value = packet["behavior_plan"]
            outcome_value = packet["outcome"]
            if not all(
                isinstance(value, Mapping)
                for value in (
                    snapshot_value,
                    record_value,
                    plan_value,
                    outcome_value,
                )
            ):
                raise MarketCycleContractError("review artifacts must be objects")
            snapshot = InputSnapshot.from_dict(snapshot_value)
            record = HypothesisRecord.from_dict(record_value)
            plan = BehaviorPlan.from_dict(plan_value)
            outcome = Outcome.from_dict(outcome_value)
        except (KeyError, TypeError, MarketCycleContractError) as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            ) from exc
        snapshot_ref = self._artifact_reference(
            packet.get("input_snapshot_ref"),
            snapshot,
            artifact_type="InputSnapshot",
            artifact_id=snapshot.snapshot_id,
        )
        record_ref = self._artifact_reference(
            packet.get("hypothesis_record_ref"),
            record,
            artifact_type="HypothesisRecord",
            artifact_id=record.record_id,
        )
        self._validate_auxiliary_context(
            packet,
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        plan_ref = self._artifact_reference(
            packet.get("behavior_plan_ref"),
            plan,
            artifact_type="BehaviorPlan",
            artifact_id=plan.plan_id,
        )
        outcome_ref = self._artifact_reference(
            packet.get("outcome_ref"),
            outcome,
            artifact_type="Outcome",
            artifact_id=outcome.outcome_id,
        )
        expected_agent_decision = AgentDecision(
            cycle_id=record.cycle_id,
            request_sha256=record.agent_request_sha256,
            theory_identity=record.theory_identity.to_dict(),
            delivered_at=record.agent_delivered_at,
            decision_text=record.agent_decision_text,
            decision_size_bytes=record.agent_decision_size_bytes,
            decision_sha256=record.agent_decision_sha256,
            delivery_path=record.agent_delivery_path,
            delivery_sha256=record.agent_delivery_sha256,
        ).to_dict()
        expected_agent_decision_ref = {
            "transport_path": record.agent_delivery_path,
            "transport_sha256": record.agent_delivery_sha256,
            "decision_sha256": record.agent_decision_sha256,
        }
        theory_identity = plan.theory_identity.to_dict()
        if (
            snapshot.cycle_id != cycle_id
            or record.cycle_id != cycle_id
            or plan.cycle_id != cycle_id
            or outcome.cycle_id != cycle_id
            or record.input_snapshot_ref != snapshot_ref
            or plan.hypothesis_record_ref != record_ref
            or outcome.behavior_plan_ref != plan_ref
            or record.theory_identity != snapshot.theory_identity
            or plan.theory_identity != record.theory_identity
            or outcome.theory_identity != plan.theory_identity
            or packet.get("theory_identity") != theory_identity
            or packet.get("agent_decision_ref") != expected_agent_decision_ref
            or packet.get("agent_decision") != expected_agent_decision
            or not isinstance(packet.get("memory_context"), Mapping)
            or not isinstance(packet.get("deterministic_calculations"), Mapping)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        requested_at = self._timestamp(
            packet.get("review_requested_at"),
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        review_due_at = self._timestamp(
            packet.get("review_due_at"),
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        outcome_sealed_at = self._timestamp(
            outcome.sealed_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        if (
            requested_at < outcome_sealed_at
            or review_due_at
            != requested_at + timedelta(seconds=_REVIEW_TIME_BUDGET_SECONDS)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        return plan, plan_ref, outcome, outcome_ref, review_due_at

    def _decision_from_delivery(
        self,
        *,
        cycle_id: str,
        request: Mapping[str, Any],
        request_snapshot: InputSnapshot,
        delivery: Mapping[str, Any],
        delivery_raw: bytes,
    ) -> AgentDecision:
        self._delivery_goal_identity(
            delivery,
            base_fields=_DECISION_DELIVERY_BASE_FIELDS,
            error_code="MARKET_CYCLE_AGENT_DELIVERY_BINDING_INVALID",
        )
        if (
            delivery.get("schema_id") != _DELIVERY_SCHEMA
            or delivery.get("cycle_id") != cycle_id
            or delivery.get("request_sha256") != request.get("packet_sha256")
            or delivery.get("theory_identity")
            != request_snapshot.theory_identity.to_dict()
            or delivery.get("media_type")
            != self._media_type_hint(delivery.get("media_type"))
            or delivery.get("encoding") != "UTF-8"
            or not isinstance(delivery.get("decision_text"), str)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_BINDING_INVALID"
            )
        try:
            decision_bytes = delivery["decision_text"].encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_CONTENT_INVALID"
            ) from exc
        decision_text, decision_size, decision_sha256 = self._decision_text(
            decision_bytes
        )
        if (
            delivery.get("decision_size_bytes") != decision_size
            or delivery.get("decision_sha256") != decision_sha256
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_CONTENT_INVALID"
            )
        delivered_at = self._timestamp(
            delivery.get("delivered_at"),
            error_code="MARKET_CYCLE_AGENT_DELIVERY_TIME_INVALID",
        )
        snapshot_sealed_at = self._timestamp(
            request_snapshot.sealed_at,
            error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
        )
        if not snapshot_sealed_at <= delivered_at < self._outcome_due_at(
            request_snapshot
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_NOT_PROSPECTIVE"
            )
        return AgentDecision(
            cycle_id=cycle_id,
            request_sha256=str(request["packet_sha256"]),
            theory_identity=dict(request_snapshot.theory_identity.to_dict()),
            delivered_at=str(delivery["delivered_at"]),
            decision_text=decision_text,
            decision_size_bytes=decision_size,
            decision_sha256=decision_sha256,
            delivery_path=_DELIVERY_RELATIVE_PATH.as_posix(),
            delivery_sha256=hashlib.sha256(delivery_raw).hexdigest(),
        )

    def _review_from_delivery(
        self,
        *,
        cycle_id: str,
        request: Mapping[str, Any],
        plan: BehaviorPlan,
        plan_ref: ArtifactRef,
        outcome: Outcome,
        outcome_ref: ArtifactRef,
        review_due_at: datetime,
        delivery: Mapping[str, Any],
        delivery_raw: bytes,
    ) -> AgentReview:
        base_fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "cycle_id",
                "request_sha256",
                "theory_identity",
                "behavior_plan_sha256",
                "outcome_sha256",
                "delivered_at",
                "media_type",
                "encoding",
                "review_size_bytes",
                "review_sha256",
                "review_text",
            }
        )
        self._delivery_goal_identity(
            delivery,
            base_fields=base_fields,
            error_code="MARKET_CYCLE_AGENT_REVIEW_DELIVERY_BINDING_INVALID",
        )
        if (
            delivery.get("schema_id") != _REVIEW_DELIVERY_SCHEMA
            or delivery.get("cycle_id") != cycle_id
            or delivery.get("request_sha256") != request.get("packet_sha256")
            or delivery.get("theory_identity") != plan.theory_identity.to_dict()
            or delivery.get("behavior_plan_sha256") != plan_ref.sha256
            or delivery.get("outcome_sha256") != outcome_ref.sha256
            or delivery.get("media_type")
            != self._media_type_hint(delivery.get("media_type"))
            or delivery.get("encoding") != "UTF-8"
            or not isinstance(delivery.get("review_text"), str)
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_BINDING_INVALID"
            )
        try:
            review_bytes = delivery["review_text"].encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_CONTENT_INVALID"
            ) from exc
        review_text, review_size, review_sha256 = self._review_text(review_bytes)
        if (
            delivery.get("review_size_bytes") != review_size
            or delivery.get("review_sha256") != review_sha256
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_CONTENT_INVALID"
            )
        delivered_at = self._timestamp(
            delivery.get("delivered_at"),
            error_code="MARKET_CYCLE_AGENT_REVIEW_DELIVERY_TIME_INVALID",
        )
        outcome_sealed_at = self._timestamp(
            outcome.sealed_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        if not outcome_sealed_at <= delivered_at < review_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_NOT_PROSPECTIVE"
            )
        return AgentReview(
            cycle_id=cycle_id,
            request_sha256=str(request["packet_sha256"]),
            theory_identity=dict(plan.theory_identity.to_dict()),
            review_requested_at=str(request["packet"]["review_requested_at"]),
            review_due_at=str(request["packet"]["review_due_at"]),
            delivered_at=str(delivery["delivered_at"]),
            review_text=review_text,
            review_size_bytes=review_size,
            review_sha256=review_sha256,
            delivery_path=_REVIEW_DELIVERY_RELATIVE_PATH.as_posix(),
            delivery_sha256=hashlib.sha256(delivery_raw).hexdigest(),
        )

    def analyze(self, packet: AgentPacket) -> AgentDecision:
        request_document = self._request_document(packet)
        self._request_snapshot(request_document, cycle_id=packet.cycle_id)
        request_path = self._request_path(packet.cycle_id)
        try:
            write_once_json(request_path, request_document)
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_CONFLICT"
            ) from exc
        request, _ = self._read(request_path)
        snapshot = self._request_snapshot(request, cycle_id=packet.cycle_id)

        delivery_path = self._delivery_path(packet.cycle_id)
        if self._path_present(delivery_path):
            delivery, delivery_raw = self._read(delivery_path)
            return self._decision_from_delivery(
                cycle_id=packet.cycle_id,
                request=request,
                request_snapshot=snapshot,
                delivery=delivery,
                delivery_raw=delivery_raw,
            )
        now = self._timestamp(
            self._clock(), error_code="MARKET_CYCLE_AGENT_DELIVERY_TIME_INVALID"
        )
        if now >= self._outcome_due_at(snapshot):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DECISION_WINDOW_EXPIRED"
            )
        raise AgentAnalysisPending(str(request_path.relative_to(self._root)))

    def review(self, packet: AgentReviewPacket) -> AgentReview:
        request_path = self._review_request_path(packet.cycle_id)
        if not self._path_present(request_path):
            request_document = self._review_request_document(
                packet,
                review_requested_at=self._clock(),
            )
            self._review_context(request_document, cycle_id=packet.cycle_id)
            try:
                write_once_json(request_path, request_document)
            except CanonicalContractError:
                pass
        request, _ = self._read(request_path)
        request_packet = request.get("packet")
        if not isinstance(request_packet, Mapping):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID"
            )
        persisted_base = dict(request_packet)
        persisted_base.pop("review_requested_at", None)
        persisted_base.pop("review_due_at", None)
        if canonical_bytes(persisted_base) != canonical_bytes(packet.to_dict()):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_CONFLICT"
            )
        plan, plan_ref, outcome, outcome_ref, review_due_at = self._review_context(
            request, cycle_id=packet.cycle_id
        )
        delivery_path = self._review_delivery_path(packet.cycle_id)
        if self._path_present(delivery_path):
            delivery, delivery_raw = self._read(delivery_path)
            return self._review_from_delivery(
                cycle_id=packet.cycle_id,
                request=request,
                plan=plan,
                plan_ref=plan_ref,
                outcome=outcome,
                outcome_ref=outcome_ref,
                review_due_at=review_due_at,
                delivery=delivery,
                delivery_raw=delivery_raw,
            )
        now = self._timestamp(
            self._clock(),
            error_code="MARKET_CYCLE_AGENT_REVIEW_DELIVERY_TIME_INVALID",
        )
        if now >= review_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_WINDOW_EXPIRED"
            )
        raise AgentReviewPending(str(request_path.relative_to(self._root)))

    def persist_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str,
        deadline_at: str,
        physical_goal_id: str | None = None,
    ) -> str:
        """Publish admitted Agent text before its frozen dispatch deadline."""

        cycle = self._cycle(cycle_id)
        if physical_goal_id is not None and (
            not isinstance(physical_goal_id, str)
            or _PHYSICAL_GOAL_ID.fullmatch(physical_goal_id) is None
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_GOAL_IDENTITY_INVALID"
            )
        media_type_hint = self._media_type_hint(media_type)
        decision_text, decision_size, decision_sha256 = self._decision_text(
            decision_bytes
        )
        request_path = self._request_path(cycle)
        if not self._path_present(request_path):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_MISSING"
            )
        request, _ = self._read(request_path)
        snapshot = self._request_snapshot(request, cycle_id=cycle)
        snapshot_sealed_at = self._timestamp(
            snapshot.sealed_at,
            error_code="MARKET_CYCLE_AGENT_REQUEST_INVALID",
        )
        outcome_due_at = self._outcome_due_at(snapshot)
        deadline = self._timestamp(
            deadline_at,
            error_code="MARKET_CYCLE_AGENT_DECISION_DEADLINE_INVALID",
        )
        if not snapshot_sealed_at < deadline <= outcome_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DECISION_DEADLINE_INVALID"
            )

        delivery_path = self._delivery_path(cycle)
        if self._path_present(delivery_path):
            delivery, delivery_raw = self._read(delivery_path)
            existing = self._decision_from_delivery(
                cycle_id=cycle,
                request=request,
                request_snapshot=snapshot,
                delivery=delivery,
                delivery_raw=delivery_raw,
            )
            if delivery.get("physical_goal_id") != physical_goal_id:
                raise MarketCycleAgentMailboxError(
                    "MARKET_CYCLE_AGENT_DELIVERY_GOAL_CONFLICT"
                )
            existing_delivered_at = self._timestamp(
                existing.delivered_at,
                error_code="MARKET_CYCLE_AGENT_DELIVERY_TIME_INVALID",
            )
            if existing_delivered_at >= deadline:
                raise AgentDecisionDeadlineExpired()
            if (
                existing.decision_text.encode("utf-8", errors="strict")
                == decision_bytes
            ):
                return "EXISTING_IDENTICAL"
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_CONFLICT"
            )

        delivered_at = self._clock()
        delivered = self._timestamp(
            delivered_at,
            error_code="MARKET_CYCLE_AGENT_DELIVERY_TIME_INVALID",
        )
        if delivered >= deadline:
            raise AgentDecisionDeadlineExpired()
        if not snapshot_sealed_at <= delivered < outcome_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_NOT_PROSPECTIVE"
            )
        document = {
            "schema_id": _DELIVERY_SCHEMA,
            "schema_version": (
                _GOAL_DELIVERY_SCHEMA_VERSION
                if physical_goal_id is not None
                else _SCHEMA_VERSION
            ),
            "cycle_id": cycle,
            "request_sha256": request["packet_sha256"],
            "theory_identity": snapshot.theory_identity.to_dict(),
            "delivered_at": delivered_at,
            "media_type": media_type_hint,
            "encoding": "UTF-8",
            "decision_size_bytes": decision_size,
            "decision_sha256": decision_sha256,
            "decision_text": decision_text,
        }
        if physical_goal_id is not None:
            document["physical_goal_id"] = physical_goal_id
        try:
            return write_once_json(delivery_path, document)
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_DELIVERY_CONFLICT"
            ) from exc

    def persist_goal_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str,
    ) -> str:
        """Seal Goal text against the request-owned prospective deadline."""

        cycle = self._cycle(cycle_id)
        request_path = self._request_path(cycle)
        if not self._path_present(request_path):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_MISSING"
            )
        request, _ = self._read(request_path)
        snapshot = self._request_snapshot(request, cycle_id=cycle)
        return self.persist_decision(
            cycle,
            decision_bytes,
            media_type=media_type,
            deadline_at=snapshot.outcome_due_at,
            physical_goal_id=self._current_goal_identity(),
        )

    def persist_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str,
        deadline_at: str,
        physical_goal_id: str | None = None,
    ) -> str:
        """Wrap and publish one verbatim Agent review after Outcome sealing."""

        cycle = self._cycle(cycle_id)
        if physical_goal_id is not None and (
            not isinstance(physical_goal_id, str)
            or _PHYSICAL_GOAL_ID.fullmatch(physical_goal_id) is None
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_GOAL_IDENTITY_INVALID"
            )
        media_type_hint = self._media_type_hint(media_type)
        review_text, review_size, review_sha256 = self._review_text(review_bytes)
        request_path = self._review_request_path(cycle)
        if not self._path_present(request_path):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_MISSING"
            )
        request, _ = self._read(request_path)
        plan, plan_ref, outcome, outcome_ref, review_due_at = self._review_context(
            request, cycle_id=cycle
        )
        outcome_sealed_at = self._timestamp(
            outcome.sealed_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
        )
        deadline = self._timestamp(
            deadline_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_DEADLINE_INVALID",
        )
        if not outcome_sealed_at < deadline <= review_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DEADLINE_INVALID"
            )

        delivery_path = self._review_delivery_path(cycle)
        if self._path_present(delivery_path):
            delivery, delivery_raw = self._read(delivery_path)
            existing = self._review_from_delivery(
                cycle_id=cycle,
                request=request,
                plan=plan,
                plan_ref=plan_ref,
                outcome=outcome,
                outcome_ref=outcome_ref,
                review_due_at=review_due_at,
                delivery=delivery,
                delivery_raw=delivery_raw,
            )
            if delivery.get("physical_goal_id") != physical_goal_id:
                raise MarketCycleAgentMailboxError(
                    "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_GOAL_CONFLICT"
                )
            existing_delivered_at = self._timestamp(
                existing.delivered_at,
                error_code="MARKET_CYCLE_AGENT_REVIEW_DELIVERY_TIME_INVALID",
            )
            if existing_delivered_at >= deadline:
                raise AgentReviewDeadlineExpired()
            if (
                existing.review_text.encode("utf-8", errors="strict") == review_bytes
            ):
                return "EXISTING_IDENTICAL"
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_CONFLICT"
            )

        delivered_at = self._clock()
        delivered = self._timestamp(
            delivered_at,
            error_code="MARKET_CYCLE_AGENT_REVIEW_DELIVERY_TIME_INVALID",
        )
        if delivered >= deadline:
            raise AgentReviewDeadlineExpired()
        if not outcome_sealed_at <= delivered < review_due_at:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_NOT_PROSPECTIVE"
            )
        document = {
            "schema_id": _REVIEW_DELIVERY_SCHEMA,
            "schema_version": (
                _GOAL_DELIVERY_SCHEMA_VERSION
                if physical_goal_id is not None
                else _SCHEMA_VERSION
            ),
            "cycle_id": cycle,
            "request_sha256": request["packet_sha256"],
            "theory_identity": plan.theory_identity.to_dict(),
            "behavior_plan_sha256": plan_ref.sha256,
            "outcome_sha256": outcome_ref.sha256,
            "delivered_at": delivered_at,
            "media_type": media_type_hint,
            "encoding": "UTF-8",
            "review_size_bytes": review_size,
            "review_sha256": review_sha256,
            "review_text": review_text,
        }
        if physical_goal_id is not None:
            document["physical_goal_id"] = physical_goal_id
        try:
            return write_once_json(delivery_path, document)
        except CanonicalContractError as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_CONFLICT"
            ) from exc

    def persist_goal_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str,
    ) -> str:
        """Seal Goal review text against the immutable review request deadline."""

        cycle = self._cycle(cycle_id)
        request_path = self._review_request_path(cycle)
        if not self._path_present(request_path):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REVIEW_REQUEST_MISSING"
            )
        request, _ = self._read(request_path)
        _, _, _, _, review_due_at = self._review_context(
            request, cycle_id=cycle
        )
        return self.persist_review(
            cycle,
            review_bytes,
            media_type=media_type,
            deadline_at=review_due_at.isoformat(),
            physical_goal_id=self._current_goal_identity(),
        )

    def request(self, cycle_id: str) -> Mapping[str, Any] | None:
        """Read any canonical request sidecar, including legacy requests, without use."""

        path = self._request_path(cycle_id)
        if not self._path_present(path):
            return None
        value, _ = self._read(path)
        return value

    def goal_decision_delivery_binding(
        self, cycle_id: str
    ) -> Mapping[str, str] | None:
        """Read and fully validate one V3.3.2 Goal delivery without advancing."""

        cycle = self._cycle(cycle_id)
        delivery_path = self._delivery_path(cycle)
        if not self._path_present(delivery_path):
            return None
        request_path = self._request_path(cycle)
        if not self._path_present(request_path):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_REQUEST_MISSING"
            )
        request, _ = self._read(request_path)
        snapshot = self._request_snapshot(request, cycle_id=cycle)
        delivery, delivery_raw = self._read(delivery_path)
        decision = self._decision_from_delivery(
            cycle_id=cycle,
            request=request,
            request_snapshot=snapshot,
            delivery=delivery,
            delivery_raw=delivery_raw,
        )
        physical_goal_id = self._delivery_goal_identity(
            delivery,
            base_fields=_DECISION_DELIVERY_BASE_FIELDS,
            error_code="MARKET_CYCLE_AGENT_GOAL_DELIVERY_BINDING_INVALID",
        )
        if physical_goal_id is None:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_GOAL_DELIVERY_BINDING_REQUIRED"
            )
        delivery_sha256 = hashlib.sha256(delivery_raw).hexdigest()
        if decision.delivery_sha256 != delivery_sha256:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_GOAL_DELIVERY_BINDING_INVALID"
            )
        return {
            "physical_goal_id": physical_goal_id,
            "delivery_sha256": delivery_sha256,
        }

    def review_request(self, cycle_id: str) -> Mapping[str, Any] | None:
        """Read the canonical Agent-review request sidecar without advancing."""

        path = self._review_request_path(cycle_id)
        if not self._path_present(path):
            return None
        value, _ = self._read(path)
        return value


__all__ = ["LocalMarketCycleAgentMailbox", "MarketCycleAgentMailboxError"]
