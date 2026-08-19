"""Pre-outcome capability contracts for Agent-owned paper decisions.

These contracts bind exact decisions, execution intents, attention requests and
ledger heads.  Human/Agent assessors supply typed findings with exact UTF-8
evidence spans; the deterministic system never infers semantic quality and no
outcome, predictive, generalization or profitability claim is produced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_bytes, canonical_decimal, canonical_digest
from .capability_evaluation import is_physical_goal_identity


PAPER_CAPABILITY_SCHEMA_ID = (
    "agent-trade-emotion.v332-pre-outcome-paper-capability-assessment"
)
PAPER_CAPABILITY_SCHEMA_VERSION = "1.3.0"
PAPER_CAPABILITY_IDS = frozenset(
    {"TRADING_DECISION", "POSITION_MANAGEMENT", "ATTENTION_SCHEDULING"}
)
PAPER_CAPABILITY_CRITERIA: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "TRADING_DECISION": (
            "LEGAL_ACTION_COMPARISON_AND_OPPORTUNITY_COST",
            "ACTIVATION_INVALIDATION_AND_EXPIRY",
            "TARGET_DELTA_RECONCILIATION",
            "RISK_AND_COST_BOUNDS",
            "ATTENTION_PLAN",
        ),
        "POSITION_MANAGEMENT": (
            "CROSS_CYCLE_CONTINUITY",
            "DECISION_RELEVANT_TRANSITION",
            "TRANCHE_AND_ROLE_DISCIPLINE",
            "NO_LOSS_AVERAGING",
            "WAIT_HYSTERESIS_AND_REARM",
        ),
        "ATTENTION_SCHEDULING": (
            "MODE_FOCUS_REASON_LINKED_TO_HYPOTHESIS_AND_INVALIDATION",
            "EARLIEST_LATEST_WINDOW_RATIONALE",
            "CONTINUE_WAKE_STOP_ESCALATE_EXPLANATION",
            "OPPORTUNITY_COST_AND_NEXT_REVIEW",
        ),
    }
)


def _paper_capability_rubric(
    capability_id: str,
    criterion_specs: tuple[tuple[str, str, str, str], ...],
) -> Mapping[str, Any]:
    criteria = tuple(
        MappingProxyType(
            {
                "criterion_id": criterion_id,
                "source_path": source_path,
                "source_section": source_section,
                "assessment_instruction": instruction,
            }
        )
        for criterion_id, source_path, source_section, instruction in criterion_specs
    )
    base: dict[str, Any] = {"capability_id": capability_id, "criteria": criteria}
    return MappingProxyType({**base, "rubric_sha256": canonical_digest(base)})


PAPER_CAPABILITY_RUBRICS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "TRADING_DECISION": _paper_capability_rubric(
            "TRADING_DECISION",
            (
                (
                    "LEGAL_ACTION_COMPARISON_AND_OPPORTUNITY_COST",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§14 完整动作比较; §23 决策相关增量、无交易区与迟滞",
                    "DEMONSTRATED only when the Agent compares decision-relevant legal "
                    "actions, explains the selected action and states the opportunity "
                    "cost of a materially different alternative.",
                ),
                (
                    "ACTIVATION_INVALIDATION_AND_EXPIRY",
                    "theory/versions/v3.3.2/03_HYPOTHESIS_SYSTEM.md",
                    "§10 从假说到最终动作; §16.1 Action Thesis 最低语义",
                    "DEMONSTRATED only when activation, hard invalidation and a bounded "
                    "expiry or review horizon prospectively constrain the action.",
                ),
                (
                    "TARGET_DELTA_RECONCILIATION",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§19.2–19.5 当前敞口、目标敞口、PositionDelta与转换计划",
                    "DEMONSTRATED only when current exposure, target exposure and the "
                    "selected PositionDelta reconcile without silently changing role or tranche.",
                ),
                (
                    "RISK_AND_COST_BOUNDS",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§22 风险预算层级与风险守恒; §26 从目标敞口到执行事实",
                    "DEMONSTRATED only when the action states bounded loss/notional or "
                    "stress exposure and treats fees, impact, carry or missing costs explicitly.",
                ),
                (
                    "ATTENTION_PLAN",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§32 注意力管理是动态交易的一部分",
                    "DEMONSTRATED only when the Agent states when to continue or review, "
                    "what to inspect and what would end, defer or escalate attention.",
                ),
            ),
        ),
        "POSITION_MANAGEMENT": _paper_capability_rubric(
            "POSITION_MANAGEMENT",
            (
                (
                    "CROSS_CYCLE_CONTINUITY",
                    "theory/versions/v3.3.2/04_EXECUTION_AND_AGENT.md",
                    "§19 五工件内的跨 cycle 连续性; §19.1 episode identity",
                    "DEMONSTRATED only when the later decision explicitly carries forward "
                    "the same episode and distinguishes retained from changed state.",
                ),
                (
                    "DECISION_RELEVANT_TRANSITION",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§11 路径驱动的实时重规划; §23 决策相关增量、无交易区与迟滞",
                    "DEMONSTRATED only when fresh evidence or elapsed opportunity changes, "
                    "or intentionally does not change, the position transition.",
                ),
                (
                    "TRANCHE_AND_ROLE_DISCIPLINE",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§6 假说—tranche 风险对齐; §21 仓位角色与独立管理义务",
                    "DEMONSTRATED only when the affected tranche and role retain a clear "
                    "purpose, risk owner and explicit migration or unchanged-state rationale.",
                ),
                (
                    "NO_LOSS_AVERAGING",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§8.1–8.2 加仓证据与亏损时的风险收缩; §20 动作集合",
                    "DEMONSTRATED only on an exact fresh losing-position observation when "
                    "the Agent does not add merely because price moved against the position; "
                    "without that mechanical losing state the criterion is UNRESOLVED.",
                ),
                (
                    "WAIT_HYSTERESIS_AND_REARM",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§14 完整动作比较; §23 决策相关增量、无交易区与迟滞",
                    "DEMONSTRATED only when HOLD/WAIT or rearm behavior states a meaningful "
                    "no-trade threshold and the fresh evidence needed to change it.",
                ),
            ),
        ),
        "ATTENTION_SCHEDULING": _paper_capability_rubric(
            "ATTENTION_SCHEDULING",
            (
                (
                    "MODE_FOCUS_REASON_LINKED_TO_HYPOTHESIS_AND_INVALIDATION",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§32 注意力管理是动态交易的一部分",
                    "DEMONSTRATED only when the selected attention mode and requested focus "
                    "are linked to a live hypothesis, position duty or invalidation.",
                ),
                (
                    "EARLIEST_LATEST_WINDOW_RATIONALE",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§32 注意力管理是动态交易的一部分",
                    "DEMONSTRATED only when the earliest useful review and latest useful "
                    "boundary are explained by the expected information or event window.",
                ),
                (
                    "CONTINUE_WAKE_STOP_ESCALATE_EXPLANATION",
                    "theory/versions/v3.3.2/02_DYNAMIC_POSITION_MANAGEMENT.md",
                    "§32 注意力管理是动态交易的一部分",
                    "DEMONSTRATED only when relevant CONTINUE_NOW, WAKE_AFTER, STOP and "
                    "ESCALATE alternatives or switching conditions are explained.",
                ),
                (
                    "OPPORTUNITY_COST_AND_NEXT_REVIEW",
                    "theory/versions/v3.3.2/09_STATE_TRANSITION_AND_EVALUATION.md",
                    "§6.13 机会成本与换手; §6.14 注意力调度",
                    "DEMONSTRATED only when attention opportunity cost and the next review "
                    "focus or stopping condition are stated without hindsight.",
                ),
            ),
        ),
    }
)
PAPER_EVIDENCE_SOURCE_KINDS = (
    "DECISION_TEXT",
    "EXECUTION_INTENT",
)
ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS = (
    "DECISION_TEXT",
    "ATTENTION_REQUEST",
)
PAPER_FINDING_STATUSES = frozenset(
    {"DEMONSTRATED", "NOT_DEMONSTRATED", "UNRESOLVED"}
)
PAPER_ASSESSMENT_VECTOR_KEYS = (
    "operational",
    "capability",
    "prediction",
    "generalization",
    "profitability",
)
PAPER_BLINDNESS_BASIS = (
    "SEALED_BEFORE_BOUND_OUTCOME_DUE_NO_EXTERNAL_INFORMATION_ISOLATION_CLAIM"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-/]{0,255}\Z")


class PaperCapabilityEvaluationError(ValueError):
    """A paper-capability evidence binding is malformed or inconsistent."""


def _identifier(value: object, *, field: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PaperCapabilityEvaluationError(f"{field} must be a safe identifier")
    return value


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PaperCapabilityEvaluationError(f"{field} must be a SHA-256 digest")
    return value


def _time(value: object, *, field: str) -> datetime:
    if type(value) is not str or not value:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    return parsed


def _text(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > 16_384
    ):
        raise PaperCapabilityEvaluationError(f"{field} must be readable UTF-8 text")
    return value


def _exact(
    value: object,
    *,
    fields: frozenset[str],
    document_type: str | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        raise PaperCapabilityEvaluationError("paper capability document fields are invalid")
    if document_type is not None and (
        value.get("schema_id") != PAPER_CAPABILITY_SCHEMA_ID
        or value.get("schema_version") != PAPER_CAPABILITY_SCHEMA_VERSION
        or value.get("document_type") != document_type
    ):
        raise PaperCapabilityEvaluationError("paper capability document schema is invalid")
    return value


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperCapabilityEvaluationError(f"{field} must be an array")
    return tuple(value)


def _rubric_document(capability_id: str) -> dict[str, Any]:
    rubric = PAPER_CAPABILITY_RUBRICS[capability_id]
    return {
        "capability_id": rubric["capability_id"],
        "criteria": [dict(item) for item in rubric["criteria"]],
        "rubric_sha256": rubric["rubric_sha256"],
    }


def _verified_rubric(value: object, *, capability_id: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PaperCapabilityEvaluationError("rubric must be an object")
    expected = _rubric_document(capability_id)
    try:
        exact = canonical_bytes(value) == canonical_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise PaperCapabilityEvaluationError("paper capability rubric is invalid") from exc
    if not exact:
        raise PaperCapabilityEvaluationError(
            "rubric does not match the frozen paper capability rubric"
        )
    return PAPER_CAPABILITY_RUBRICS[capability_id]


def _decimal(value: object, *, field: str, nonnegative: bool = False) -> Decimal:
    if type(value) is not str:
        raise PaperCapabilityEvaluationError(f"{field} must be a canonical decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PaperCapabilityEvaluationError(
            f"{field} must be a canonical decimal"
        ) from exc
    if (
        not parsed.is_finite()
        or canonical_decimal(parsed) != value
        or (nonnegative and parsed < 0)
    ):
        raise PaperCapabilityEvaluationError(f"{field} must be a canonical decimal")
    return parsed


@dataclass(frozen=True, slots=True)
class PositionMechanicalEvidenceV1:
    """Exact D0 bracket and D1 paper-account facts qualifying position evidence."""

    d0_cycle_id: str
    d1_cycle_id: str
    account_id: str
    symbol: str
    episode_id: str
    d0_intent_sha256: str
    d0_bracket_sha256: str
    d0_entry_order_id: str
    d0_protective_stop_order_id: str
    d1_snapshot_sha256: str
    d1_paper_context_sha256: str
    d1_account_sha256: str
    d1_orders_and_fills_sha256: str
    d1_valuation_sha256: str
    d1_ledger_revision: int
    d1_ledger_head_sha256: str
    d1_account_version: int
    entry_fill_ids: tuple[str, ...]
    entry_fill_sha256s: tuple[str, ...]
    entry_filled_quantity: str
    position_signed_quantity: str
    position_abs_quantity: str
    protective_stop_order_sha256: str
    protective_stop_command_type: str
    protective_stop_state: str
    protective_stop_side: str
    protective_stop_reduce_only: bool
    protective_stop_remaining_quantity: str
    valuation_status: str
    valuation_mark: str | None
    valuation_unrealized_pnl: str | None
    valuation_observed_at: str | None
    valuation_available_at: str | None
    valuation_source_sha256: str | None
    valuation_mark_binding_status: str
    loss_observation_status: str

    def __post_init__(self) -> None:
        for field in (
            "d0_cycle_id",
            "d1_cycle_id",
            "account_id",
            "symbol",
            "episode_id",
            "d0_entry_order_id",
            "d0_protective_stop_order_id",
            "valuation_status",
        ):
            _identifier(getattr(self, field), field=field)
        for field in (
            "d0_intent_sha256",
            "d0_bracket_sha256",
            "d1_snapshot_sha256",
            "d1_paper_context_sha256",
            "d1_account_sha256",
            "d1_orders_and_fills_sha256",
            "d1_valuation_sha256",
            "d1_ledger_head_sha256",
            "protective_stop_order_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        if (
            type(self.d1_ledger_revision) is not int
            or type(self.d1_account_version) is not int
            or self.d1_ledger_revision < 1
            or self.d1_account_version != self.d1_ledger_revision
        ):
            raise PaperCapabilityEvaluationError(
                "D1 account version must bind the exact ledger revision"
            )
        fill_ids = tuple(self.entry_fill_ids)
        fill_hashes = tuple(self.entry_fill_sha256s)
        if not fill_ids or len(fill_ids) != len(fill_hashes):
            raise PaperCapabilityEvaluationError(
                "D0 entry requires exact D1 fill identities and digests"
            )
        for index, value in enumerate(fill_ids):
            _identifier(value, field=f"entry_fill_ids[{index}]")
        for index, value in enumerate(fill_hashes):
            _sha256(value, field=f"entry_fill_sha256s[{index}]")
        if len(fill_ids) != len(set(fill_ids)):
            raise PaperCapabilityEvaluationError("entry fill identities must be unique")
        entry_filled = _decimal(
            self.entry_filled_quantity,
            field="entry_filled_quantity",
            nonnegative=True,
        )
        signed = _decimal(self.position_signed_quantity, field="position_signed_quantity")
        absolute = _decimal(
            self.position_abs_quantity,
            field="position_abs_quantity",
            nonnegative=True,
        )
        stop_remaining = _decimal(
            self.protective_stop_remaining_quantity,
            field="protective_stop_remaining_quantity",
            nonnegative=True,
        )
        if entry_filled <= 0 or signed == 0 or absolute != abs(signed):
            raise PaperCapabilityEvaluationError(
                "position evidence requires an actual entry fill and non-zero D1 position"
            )
        if (
            self.protective_stop_command_type != "STOP_LOSS"
            or self.protective_stop_state not in {"OPEN", "PARTIALLY_FILLED"}
            or type(self.protective_stop_reduce_only) is not bool
            or not self.protective_stop_reduce_only
            or self.protective_stop_side
            != ("SELL" if signed > 0 else "BUY")
            or stop_remaining < absolute
        ):
            raise PaperCapabilityEvaluationError(
                "D1 position must retain an active sufficient opposite reduce-only STOP_LOSS"
            )
        if self.valuation_mark_binding_status not in {
            "FRESH_SNAPSHOT_BOUND",
            "UNKNOWN_NOT_FRESH_OR_COMPLETE",
        }:
            raise PaperCapabilityEvaluationError(
                "valuation_mark_binding_status is invalid"
            )
        if self.loss_observation_status not in {
            "LOSING_FRESH_MARK",
            "NON_LOSING_FRESH_MARK",
            "UNKNOWN_NOT_FRESH_OR_COMPLETE",
        }:
            raise PaperCapabilityEvaluationError("loss_observation_status is invalid")
        if self.valuation_mark_binding_status == "FRESH_SNAPSHOT_BOUND":
            if any(
                value is None
                for value in (
                    self.valuation_mark,
                    self.valuation_unrealized_pnl,
                    self.valuation_observed_at,
                    self.valuation_available_at,
                    self.valuation_source_sha256,
                )
            ):
                raise PaperCapabilityEvaluationError(
                    "fresh valuation requires exact mark, PnL, times and source"
                )
            _decimal(self.valuation_mark, field="valuation_mark", nonnegative=True)
            unrealized = _decimal(
                self.valuation_unrealized_pnl, field="valuation_unrealized_pnl"
            )
            _time(self.valuation_observed_at, field="valuation_observed_at")
            _time(self.valuation_available_at, field="valuation_available_at")
            _sha256(self.valuation_source_sha256, field="valuation_source_sha256")
            expected_loss = (
                "LOSING_FRESH_MARK" if unrealized < 0 else "NON_LOSING_FRESH_MARK"
            )
            if self.loss_observation_status != expected_loss:
                raise PaperCapabilityEvaluationError(
                    "loss observation does not match exact fresh unrealized PnL"
                )
        elif self.loss_observation_status != "UNKNOWN_NOT_FRESH_OR_COMPLETE":
            raise PaperCapabilityEvaluationError(
                "non-fresh valuation cannot claim a loss observation"
            )
        object.__setattr__(self, "entry_fill_ids", fill_ids)
        object.__setattr__(self, "entry_fill_sha256s", fill_hashes)

    @property
    def evidence_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            field: (
                list(getattr(self, field))
                if field in {"entry_fill_ids", "entry_fill_sha256s"}
                else getattr(self, field)
            )
            for field in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PositionMechanicalEvidenceV1":
        fields = frozenset(cls.__dataclass_fields__)
        document = _exact(value, fields=fields)
        kwargs = dict(document)
        kwargs["entry_fill_ids"] = _sequence(
            document["entry_fill_ids"], field="entry_fill_ids"
        )
        kwargs["entry_fill_sha256s"] = _sequence(
            document["entry_fill_sha256s"], field="entry_fill_sha256s"
        )
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class PaperEvidenceSpanV1:
    """A half-open byte span into one exact Agent-owned UTF-8 source."""

    cycle_id: str
    source_kind: str
    source_sha256: str
    start_byte: int
    end_byte: int
    selected_utf8_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.cycle_id, field="cycle_id")
        if self.source_kind not in frozenset(
            PAPER_EVIDENCE_SOURCE_KINDS
            + ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS
        ):
            raise PaperCapabilityEvaluationError("source_kind is unsupported")
        _sha256(self.source_sha256, field="source_sha256")
        _sha256(self.selected_utf8_sha256, field="selected_utf8_sha256")
        if (
            type(self.start_byte) is not int
            or type(self.end_byte) is not int
            or self.start_byte < 0
            or self.end_byte <= self.start_byte
        ):
            raise PaperCapabilityEvaluationError(
                "paper evidence span must be a non-empty half-open byte range"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "source_kind": self.source_kind,
            "source_sha256": self.source_sha256,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "selected_utf8_sha256": self.selected_utf8_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperEvidenceSpanV1":
        document = _exact(
            value,
            fields=frozenset(
                {
                    "cycle_id",
                    "source_kind",
                    "source_sha256",
                    "start_byte",
                    "end_byte",
                    "selected_utf8_sha256",
                }
            ),
        )
        return cls(**dict(document))


@dataclass(frozen=True, slots=True)
class PaperCapabilityFindingV1:
    """One assessor-owned criterion judgment, without automatic semantics."""

    criterion_id: str
    status: str
    rationale: str
    evidence_spans: tuple[PaperEvidenceSpanV1, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.criterion_id, field="criterion_id")
        if self.status not in PAPER_FINDING_STATUSES:
            raise PaperCapabilityEvaluationError("finding status is unsupported")
        _text(self.rationale, field="rationale")
        spans = tuple(self.evidence_spans)
        if not all(isinstance(item, PaperEvidenceSpanV1) for item in spans):
            raise PaperCapabilityEvaluationError(
                "evidence_spans must contain PaperEvidenceSpanV1"
            )
        if self.status == "DEMONSTRATED" and not spans:
            raise PaperCapabilityEvaluationError(
                "DEMONSTRATED finding requires exact Agent-owned evidence"
            )
        object.__setattr__(self, "evidence_spans", spans)

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "rationale": self.rationale,
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperCapabilityFindingV1":
        document = _exact(
            value,
            fields=frozenset(
                {"criterion_id", "status", "rationale", "evidence_spans"}
            ),
        )
        try:
            spans = tuple(
                PaperEvidenceSpanV1.from_dict(item)
                for item in _sequence(document["evidence_spans"], field="evidence_spans")
            )
        except (TypeError, PaperCapabilityEvaluationError) as exc:
            raise PaperCapabilityEvaluationError(
                "evidence_spans contain an invalid span"
            ) from exc
        return cls(
            criterion_id=document["criterion_id"],
            status=document["status"],
            rationale=document["rationale"],
            evidence_spans=spans,
        )


@dataclass(frozen=True, slots=True)
class BoundPaperDecisionPointV1:
    """Digest-only binding of one exact pre-outcome paper decision point."""

    cycle_id: str
    snapshot_id: str
    snapshot_sha256: str
    snapshot_sealed_at: str
    outcome_due_at: str
    request_sha256: str
    request_document_sha256: str
    decision_sha256: str
    hypothesis_record_sha256: str
    decision_size_bytes: int
    decision_sealed_at: str
    intent_id: str
    intent_sha256: str
    intent_request_sha256: str
    paper_context_sha256: str
    intent_authored_at: str
    intent_valid_until: str
    action: str
    account_id: str
    logical_agent_id: str
    physical_task_id: str
    agent_generation: int
    symbol: str
    episode_id: str
    transition_id: str
    tranche_id: str | None
    role: str
    pre_ledger_revision: int
    pre_ledger_head_sha256: str
    post_ledger_revision: int
    post_ledger_head_sha256: str
    post_ledger_occurred_at: str
    lawful_actions: tuple[str, ...]
    prior_intent_sha256s: tuple[str, ...]
    cycle_completion_status: str
    prior_decision_status: str
    prior_complete_cycle_id: str | None
    prior_complete_intent_sha256: str | None
    prior_complete_artifact_sha256s: Mapping[str, str]
    episode_exposure_projection_status: str
    episode_exposure_projection_sha256: str
    position_mechanical_evidence: PositionMechanicalEvidenceV1 | None
    source_sha256s: Mapping[str, str]

    def __post_init__(self) -> None:
        for field in (
            "cycle_id",
            "snapshot_id",
            "intent_id",
            "action",
            "account_id",
            "logical_agent_id",
            "physical_task_id",
            "symbol",
            "episode_id",
            "transition_id",
            "role",
        ):
            _identifier(getattr(self, field), field=field)
        if self.tranche_id is not None:
            _identifier(self.tranche_id, field="tranche_id")
        for field in (
            "snapshot_sha256",
            "request_sha256",
            "request_document_sha256",
            "decision_sha256",
            "hypothesis_record_sha256",
            "intent_sha256",
            "intent_request_sha256",
            "paper_context_sha256",
            "pre_ledger_head_sha256",
            "post_ledger_head_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        for field in (
            "snapshot_sealed_at",
            "outcome_due_at",
            "decision_sealed_at",
            "intent_authored_at",
            "intent_valid_until",
            "post_ledger_occurred_at",
        ):
            _time(getattr(self, field), field=field)
        if not (
            _time(self.snapshot_sealed_at, field="snapshot_sealed_at")
            <= _time(self.decision_sealed_at, field="decision_sealed_at")
            <= _time(self.intent_authored_at, field="intent_authored_at")
            <= _time(self.post_ledger_occurred_at, field="post_ledger_occurred_at")
            < _time(self.outcome_due_at, field="outcome_due_at")
        ):
            raise PaperCapabilityEvaluationError(
                "paper decision point chronology is invalid"
            )
        if _time(self.intent_valid_until, field="intent_valid_until") < _time(
            self.post_ledger_occurred_at, field="post_ledger_occurred_at"
        ):
            raise PaperCapabilityEvaluationError("intent expired before ledger admission")
        if type(self.decision_size_bytes) is not int or self.decision_size_bytes < 1:
            raise PaperCapabilityEvaluationError(
                "decision_size_bytes must be a positive integer"
            )
        if type(self.agent_generation) is not int or self.agent_generation < 1:
            raise PaperCapabilityEvaluationError("agent_generation must be >= 1")
        if (
            type(self.pre_ledger_revision) is not int
            or type(self.post_ledger_revision) is not int
            or self.pre_ledger_revision < 1
            or self.post_ledger_revision != self.pre_ledger_revision + 1
        ):
            raise PaperCapabilityEvaluationError(
                "ledger heads must describe one exact admitted intent transition"
            )
        lawful = tuple(self.lawful_actions)
        if not lawful or any(type(item) is not str or not item for item in lawful):
            raise PaperCapabilityEvaluationError("lawful_actions must be non-empty text")
        prior = tuple(self.prior_intent_sha256s)
        for index, value in enumerate(prior):
            _sha256(value, field=f"prior_intent_sha256s[{index}]")
        if len(prior) != len(set(prior)):
            raise PaperCapabilityEvaluationError("prior intents must be unique")
        if self.cycle_completion_status not in {"COMPLETE", "PRE_OUTCOME"}:
            raise PaperCapabilityEvaluationError(
                "cycle_completion_status must be COMPLETE or PRE_OUTCOME"
            )
        if self.prior_decision_status not in {
            "NO_PRIOR_INTENT",
            "UNAVAILABLE_CYCLE_REPOSITORY",
            "UNAVAILABLE_PRIOR_DECISION_ARTIFACT",
            "PRIOR_OUTCOME_REVIEW_PENDING",
            "PRIOR_COMPLETE_OBSERVED",
        }:
            raise PaperCapabilityEvaluationError("prior_decision_status is invalid")
        artifact_keys = frozenset(
            {"HypothesisRecord", "BehaviorPlan", "Outcome", "Review"}
        )
        if self.prior_decision_status == "PRIOR_COMPLETE_OBSERVED":
            if self.prior_complete_cycle_id is None:
                raise PaperCapabilityEvaluationError(
                    "complete prior decision identity is incomplete"
                )
            _identifier(self.prior_complete_cycle_id, field="prior_complete_cycle_id")
            if self.prior_complete_intent_sha256 is not None:
                _sha256(
                    self.prior_complete_intent_sha256,
                    field="prior_complete_intent_sha256",
                )
            if (
                not isinstance(self.prior_complete_artifact_sha256s, Mapping)
                or frozenset(self.prior_complete_artifact_sha256s) != artifact_keys
            ):
                raise PaperCapabilityEvaluationError(
                    "complete prior decision artifact bindings are incomplete"
                )
            prior_artifacts = {
                key: _sha256(
                    self.prior_complete_artifact_sha256s[key],
                    field=f"prior_complete_artifact_sha256s.{key}",
                )
                for key in sorted(artifact_keys)
            }
        else:
            if (
                self.prior_complete_cycle_id is not None
                or self.prior_complete_intent_sha256 is not None
                or dict(self.prior_complete_artifact_sha256s)
            ):
                raise PaperCapabilityEvaluationError(
                    "incomplete prior decision cannot carry complete artifact bindings"
                )
            prior_artifacts = {}
        if self.episode_exposure_projection_status not in {
            "NO_PRIOR_INTENT",
            "DERIVED_UNAMBIGUOUS",
            "AMBIGUOUS",
            "UNKNOWN",
        }:
            raise PaperCapabilityEvaluationError(
                "episode exposure projection status is invalid"
            )
        _sha256(
            self.episode_exposure_projection_sha256,
            field="episode_exposure_projection_sha256",
        )
        if self.position_mechanical_evidence is not None:
            if not isinstance(
                self.position_mechanical_evidence, PositionMechanicalEvidenceV1
            ):
                raise PaperCapabilityEvaluationError(
                    "position_mechanical_evidence must be typed exact facts"
                )
            mechanical = self.position_mechanical_evidence
            if (
                mechanical.d1_cycle_id != self.cycle_id
                or mechanical.account_id != self.account_id
                or mechanical.symbol != self.symbol
                or mechanical.episode_id != self.episode_id
                or mechanical.d1_snapshot_sha256 != self.snapshot_sha256
                or mechanical.d1_paper_context_sha256 != self.paper_context_sha256
                or mechanical.d1_ledger_revision != self.pre_ledger_revision
                or mechanical.d1_ledger_head_sha256 != self.pre_ledger_head_sha256
            ):
                raise PaperCapabilityEvaluationError(
                    "position mechanical facts do not bind this D1 decision point"
                )
        if (
            not isinstance(self.source_sha256s, Mapping)
            or frozenset(self.source_sha256s)
            != frozenset(PAPER_EVIDENCE_SOURCE_KINDS)
        ):
            raise PaperCapabilityEvaluationError("source_sha256s are incomplete")
        sources = {
            kind: _sha256(self.source_sha256s[kind], field=f"source_sha256s.{kind}")
            for kind in PAPER_EVIDENCE_SOURCE_KINDS
        }
        if (
            sources["DECISION_TEXT"] != self.decision_sha256
            or sources["EXECUTION_INTENT"] != self.intent_sha256
        ):
            raise PaperCapabilityEvaluationError(
                "source digests do not bind decision and intent"
            )
        object.__setattr__(self, "lawful_actions", lawful)
        object.__setattr__(self, "prior_intent_sha256s", prior)
        object.__setattr__(
            self,
            "prior_complete_artifact_sha256s",
            MappingProxyType(prior_artifacts),
        )
        object.__setattr__(self, "source_sha256s", MappingProxyType(sources))

    @property
    def point_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def evidence_ready_at(self) -> datetime:
        return _time(
            self.post_ledger_occurred_at, field="post_ledger_occurred_at"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_sealed_at": self.snapshot_sealed_at,
            "outcome_due_at": self.outcome_due_at,
            "request_sha256": self.request_sha256,
            "request_document_sha256": self.request_document_sha256,
            "decision_sha256": self.decision_sha256,
            "hypothesis_record_sha256": self.hypothesis_record_sha256,
            "decision_size_bytes": self.decision_size_bytes,
            "decision_sealed_at": self.decision_sealed_at,
            "intent_id": self.intent_id,
            "intent_sha256": self.intent_sha256,
            "intent_request_sha256": self.intent_request_sha256,
            "paper_context_sha256": self.paper_context_sha256,
            "intent_authored_at": self.intent_authored_at,
            "intent_valid_until": self.intent_valid_until,
            "action": self.action,
            "account_id": self.account_id,
            "logical_agent_id": self.logical_agent_id,
            "physical_task_id": self.physical_task_id,
            "agent_generation": self.agent_generation,
            "symbol": self.symbol,
            "episode_id": self.episode_id,
            "transition_id": self.transition_id,
            "tranche_id": self.tranche_id,
            "role": self.role,
            "pre_ledger_revision": self.pre_ledger_revision,
            "pre_ledger_head_sha256": self.pre_ledger_head_sha256,
            "post_ledger_revision": self.post_ledger_revision,
            "post_ledger_head_sha256": self.post_ledger_head_sha256,
            "post_ledger_occurred_at": self.post_ledger_occurred_at,
            "lawful_actions": list(self.lawful_actions),
            "prior_intent_sha256s": list(self.prior_intent_sha256s),
            "cycle_completion_status": self.cycle_completion_status,
            "prior_decision_status": self.prior_decision_status,
            "prior_complete_cycle_id": self.prior_complete_cycle_id,
            "prior_complete_intent_sha256": self.prior_complete_intent_sha256,
            "prior_complete_artifact_sha256s": dict(
                self.prior_complete_artifact_sha256s
            ),
            "episode_exposure_projection_status": (
                self.episode_exposure_projection_status
            ),
            "episode_exposure_projection_sha256": (
                self.episode_exposure_projection_sha256
            ),
            "position_mechanical_evidence": (
                None
                if self.position_mechanical_evidence is None
                else self.position_mechanical_evidence.to_dict()
            ),
            "source_sha256s": dict(self.source_sha256s),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BoundPaperDecisionPointV1":
        fields = frozenset(
            {
                "cycle_id", "snapshot_id", "snapshot_sha256", "snapshot_sealed_at",
                "outcome_due_at", "request_sha256", "request_document_sha256",
                "decision_sha256", "hypothesis_record_sha256",
                "decision_size_bytes", "decision_sealed_at",
                "intent_id", "intent_sha256", "intent_request_sha256",
                "paper_context_sha256", "intent_authored_at", "intent_valid_until",
                "action", "account_id", "logical_agent_id", "physical_task_id",
                "agent_generation",
                "symbol", "episode_id", "transition_id", "tranche_id", "role",
                "pre_ledger_revision", "pre_ledger_head_sha256",
                "post_ledger_revision", "post_ledger_head_sha256",
                "post_ledger_occurred_at", "lawful_actions",
                "prior_intent_sha256s", "cycle_completion_status",
                "prior_decision_status", "prior_complete_cycle_id",
                "prior_complete_intent_sha256",
                "prior_complete_artifact_sha256s",
                "episode_exposure_projection_status",
                "episode_exposure_projection_sha256",
                "position_mechanical_evidence", "source_sha256s",
            }
        )
        document = _exact(value, fields=fields)
        kwargs = dict(document)
        kwargs["lawful_actions"] = _sequence(document["lawful_actions"], field="lawful_actions")
        kwargs["prior_intent_sha256s"] = _sequence(
            document["prior_intent_sha256s"], field="prior_intent_sha256s"
        )
        kwargs["position_mechanical_evidence"] = (
            None
            if document["position_mechanical_evidence"] is None
            else PositionMechanicalEvidenceV1.from_dict(
                document["position_mechanical_evidence"]
            )
        )
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class BoundAttentionSchedulingPointV1:
    """One Goal-owned checkpoint plus the real next decision it governed."""

    cycle_id: str
    snapshot_id: str
    snapshot_sha256: str
    snapshot_sealed_at: str
    outcome_due_at: str
    request_sha256: str
    request_document_sha256: str
    decision_sha256: str
    decision_size_bytes: int
    decision_sealed_at: str
    behavior_plan_id: str
    behavior_plan_sha256: str
    behavior_plan_sealed_at: str
    paper_context_sha256: str
    account_id: str
    logical_agent_id: str
    physical_task_id: str
    agent_generation: int
    continuity_nonce: str
    symbol: str
    pre_ledger_revision: int
    pre_ledger_head_sha256: str
    data_slice_sha256: str
    data_cursor: str
    attention_request_id: str
    attention_sha256: str
    attention_mode: str
    attention_issued_at: str
    attention_checkpoint_document_sha256: str
    attention_checkpoint_event_sha256: str
    attention_checkpoint_revision: int
    attention_checkpoint_accepted_at: str
    attention_stream_head_document_sha256: str
    attention_stream_head_event_sha256: str
    attention_stream_head_revision: int
    self_selected_window_start_at: str
    self_selected_window_end_at: str
    followup_decision_at: str
    followup_window_status: str
    source_sha256s: Mapping[str, str]

    def __post_init__(self) -> None:
        for field in (
            "cycle_id",
            "snapshot_id",
            "behavior_plan_id",
            "account_id",
            "logical_agent_id",
            "physical_task_id",
            "continuity_nonce",
            "symbol",
            "data_cursor",
            "attention_request_id",
            "attention_mode",
        ):
            _identifier(getattr(self, field), field=field)
        for field in (
            "snapshot_sha256",
            "request_sha256",
            "request_document_sha256",
            "decision_sha256",
            "behavior_plan_sha256",
            "paper_context_sha256",
            "pre_ledger_head_sha256",
            "data_slice_sha256",
            "attention_sha256",
            "attention_checkpoint_document_sha256",
            "attention_checkpoint_event_sha256",
            "attention_stream_head_document_sha256",
            "attention_stream_head_event_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        for field in (
            "snapshot_sealed_at",
            "outcome_due_at",
            "decision_sealed_at",
            "behavior_plan_sealed_at",
            "attention_issued_at",
            "attention_checkpoint_accepted_at",
            "self_selected_window_start_at",
            "self_selected_window_end_at",
            "followup_decision_at",
        ):
            _time(getattr(self, field), field=field)
        snapshot = _time(self.snapshot_sealed_at, field="snapshot_sealed_at")
        decision = _time(self.decision_sealed_at, field="decision_sealed_at")
        plan = _time(self.behavior_plan_sealed_at, field="behavior_plan_sealed_at")
        attention_issued = _time(self.attention_issued_at, field="attention_issued_at")
        accepted = _time(
            self.attention_checkpoint_accepted_at,
            field="attention_checkpoint_accepted_at",
        )
        window_start = _time(
            self.self_selected_window_start_at,
            field="self_selected_window_start_at",
        )
        window_end = _time(
            self.self_selected_window_end_at,
            field="self_selected_window_end_at",
        )
        followup = _time(self.followup_decision_at, field="followup_decision_at")
        outcome = _time(self.outcome_due_at, field="outcome_due_at")
        if not (
            attention_issued <= accepted <= followup <= decision <= plan < outcome
            and snapshot <= decision
        ):
            raise PaperCapabilityEvaluationError(
                "attention scheduling point chronology is invalid"
            )
        if not attention_issued <= window_start <= window_end:
            raise PaperCapabilityEvaluationError(
                "self-selected attention window is invalid"
            )
        expected_window_status = (
            "BEFORE_SELF_SELECTED_WINDOW"
            if followup < window_start
            else "AFTER_SELF_SELECTED_WINDOW"
            if followup > window_end
            else "WITHIN_SELF_SELECTED_WINDOW"
        )
        if self.followup_window_status != expected_window_status:
            raise PaperCapabilityEvaluationError(
                "followup_window_status does not match the exact decision time"
            )
        if type(self.decision_size_bytes) is not int or self.decision_size_bytes < 1:
            raise PaperCapabilityEvaluationError(
                "decision_size_bytes must be a positive integer"
            )
        if type(self.agent_generation) is not int or self.agent_generation < 1:
            raise PaperCapabilityEvaluationError("agent_generation must be >= 1")
        if type(self.pre_ledger_revision) is not int or self.pre_ledger_revision < 1:
            raise PaperCapabilityEvaluationError("pre_ledger_revision must be >= 1")
        if (
            type(self.attention_checkpoint_revision) is not int
            or self.attention_checkpoint_revision < 2
            or type(self.attention_stream_head_revision) is not int
            or self.attention_stream_head_revision
            != self.attention_checkpoint_revision
            or self.attention_stream_head_event_sha256
            != self.attention_checkpoint_event_sha256
        ):
            raise PaperCapabilityEvaluationError(
                "attention checkpoint must be the exact frozen stream head"
            )
        expected_kinds = frozenset(ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS)
        if (
            not isinstance(self.source_sha256s, Mapping)
            or frozenset(self.source_sha256s) != expected_kinds
        ):
            raise PaperCapabilityEvaluationError(
                "attention scheduling source_sha256s are incomplete"
            )
        sources = {
            kind: _sha256(self.source_sha256s[kind], field=f"source_sha256s.{kind}")
            for kind in ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS
        }
        if (
            sources["DECISION_TEXT"] != self.decision_sha256
            or sources["ATTENTION_REQUEST"] != self.attention_sha256
        ):
            raise PaperCapabilityEvaluationError(
                "attention scheduling source digests do not bind Agent-owned evidence"
            )
        object.__setattr__(self, "source_sha256s", MappingProxyType(sources))

    @property
    def point_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def evidence_ready_at(self) -> datetime:
        return _time(self.followup_decision_at, field="followup_decision_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_sealed_at": self.snapshot_sealed_at,
            "outcome_due_at": self.outcome_due_at,
            "request_sha256": self.request_sha256,
            "request_document_sha256": self.request_document_sha256,
            "decision_sha256": self.decision_sha256,
            "decision_size_bytes": self.decision_size_bytes,
            "decision_sealed_at": self.decision_sealed_at,
            "behavior_plan_id": self.behavior_plan_id,
            "behavior_plan_sha256": self.behavior_plan_sha256,
            "behavior_plan_sealed_at": self.behavior_plan_sealed_at,
            "paper_context_sha256": self.paper_context_sha256,
            "account_id": self.account_id,
            "logical_agent_id": self.logical_agent_id,
            "physical_task_id": self.physical_task_id,
            "agent_generation": self.agent_generation,
            "continuity_nonce": self.continuity_nonce,
            "symbol": self.symbol,
            "pre_ledger_revision": self.pre_ledger_revision,
            "pre_ledger_head_sha256": self.pre_ledger_head_sha256,
            "data_slice_sha256": self.data_slice_sha256,
            "data_cursor": self.data_cursor,
            "attention_request_id": self.attention_request_id,
            "attention_sha256": self.attention_sha256,
            "attention_mode": self.attention_mode,
            "attention_issued_at": self.attention_issued_at,
            "attention_checkpoint_document_sha256": (
                self.attention_checkpoint_document_sha256
            ),
            "attention_checkpoint_event_sha256": (
                self.attention_checkpoint_event_sha256
            ),
            "attention_checkpoint_revision": self.attention_checkpoint_revision,
            "attention_checkpoint_accepted_at": (
                self.attention_checkpoint_accepted_at
            ),
            "attention_stream_head_document_sha256": (
                self.attention_stream_head_document_sha256
            ),
            "attention_stream_head_event_sha256": (
                self.attention_stream_head_event_sha256
            ),
            "attention_stream_head_revision": self.attention_stream_head_revision,
            "self_selected_window_start_at": self.self_selected_window_start_at,
            "self_selected_window_end_at": self.self_selected_window_end_at,
            "followup_decision_at": self.followup_decision_at,
            "followup_window_status": self.followup_window_status,
            "source_sha256s": dict(self.source_sha256s),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "BoundAttentionSchedulingPointV1":
        fields = frozenset(
            {
                "cycle_id", "snapshot_id", "snapshot_sha256", "snapshot_sealed_at",
                "outcome_due_at", "request_sha256", "request_document_sha256",
                "decision_sha256", "decision_size_bytes", "decision_sealed_at",
                "behavior_plan_id", "behavior_plan_sha256",
                "behavior_plan_sealed_at", "paper_context_sha256", "account_id",
                "logical_agent_id", "physical_task_id", "agent_generation",
                "continuity_nonce", "symbol", "pre_ledger_revision",
                "pre_ledger_head_sha256", "data_slice_sha256", "data_cursor",
                "attention_request_id", "attention_sha256", "attention_mode",
                "attention_issued_at", "attention_checkpoint_document_sha256",
                "attention_checkpoint_event_sha256", "attention_checkpoint_revision",
                "attention_checkpoint_accepted_at",
                "attention_stream_head_document_sha256",
                "attention_stream_head_event_sha256",
                "attention_stream_head_revision", "self_selected_window_start_at",
                "self_selected_window_end_at", "followup_decision_at",
                "followup_window_status", "source_sha256s",
            }
        )
        return cls(**dict(_exact(value, fields=fields)))


@dataclass(frozen=True, slots=True)
class PreOutcomePaperCapabilityTaskV1:
    """One fixed-criteria assessor task bound to exact paper evidence points."""

    task_id: str
    capability_id: str
    policy_sha256: str
    subject_agent_id: str
    assessor_id: str
    created_at: str
    assessment_due_at: str
    criteria: tuple[str, ...]
    rubric: Mapping[str, Any]
    decision_points: tuple[
        BoundPaperDecisionPointV1 | BoundAttentionSchedulingPointV1, ...
    ]

    def __post_init__(self) -> None:
        for field in ("task_id", "subject_agent_id", "assessor_id"):
            _identifier(getattr(self, field), field=field)
        if self.capability_id not in PAPER_CAPABILITY_IDS:
            raise PaperCapabilityEvaluationError("capability_id is unsupported")
        _sha256(self.policy_sha256, field="policy_sha256")
        if self.subject_agent_id == self.assessor_id:
            raise PaperCapabilityEvaluationError(
                "assessor must be independent from the subject Agent identity"
            )
        if not is_physical_goal_identity(self.subject_agent_id):
            raise PaperCapabilityEvaluationError(
                "subject_agent_id must be a physical Codex Goal identity"
            )
        if self.assessor_id != "pending-capability-assessor" and not (
            is_physical_goal_identity(self.assessor_id)
        ):
            raise PaperCapabilityEvaluationError(
                "assessor_id must be a physical Codex Goal identity"
            )
        created = _time(self.created_at, field="created_at")
        due = _time(self.assessment_due_at, field="assessment_due_at")
        if due <= created:
            raise PaperCapabilityEvaluationError(
                "assessment_due_at must follow task creation"
            )
        criteria = tuple(self.criteria)
        if criteria != PAPER_CAPABILITY_CRITERIA[self.capability_id]:
            raise PaperCapabilityEvaluationError(
                "task criteria do not match the selected paper capability"
            )
        points = tuple(self.decision_points)
        expected_type = (
            BoundAttentionSchedulingPointV1
            if self.capability_id == "ATTENTION_SCHEDULING"
            else BoundPaperDecisionPointV1
        )
        if not all(isinstance(item, expected_type) for item in points):
            raise PaperCapabilityEvaluationError(
                "decision_points do not match the selected capability evidence type"
            )
        if self.capability_id == "TRADING_DECISION" and len(points) != 1:
            raise PaperCapabilityEvaluationError(
                "TRADING_DECISION requires exactly one decision point"
            )
        if self.capability_id == "POSITION_MANAGEMENT" and len(points) < 2:
            raise PaperCapabilityEvaluationError(
                "POSITION_MANAGEMENT requires at least two decision points"
            )
        if self.capability_id == "ATTENTION_SCHEDULING" and len(points) < 1:
            raise PaperCapabilityEvaluationError(
                "ATTENTION_SCHEDULING requires a checkpoint followed by a real decision"
            )
        if not points:
            raise PaperCapabilityEvaluationError("decision_points cannot be empty")
        if created < max(item.evidence_ready_at for item in points):
            raise PaperCapabilityEvaluationError(
                "task cannot precede its bound paper evidence"
            )
        outcome_deadlines = (
            (_time(points[-1].outcome_due_at, field="outcome_due_at"),)
            if self.capability_id == "POSITION_MANAGEMENT"
            else tuple(
                _time(item.outcome_due_at, field="outcome_due_at")
                for item in points
            )
        )
        if due >= min(outcome_deadlines):
            raise PaperCapabilityEvaluationError(
                "assessment deadline must precede the current bound Outcome"
            )
        if any(item.physical_task_id != self.subject_agent_id for item in points):
            raise PaperCapabilityEvaluationError(
                "task subject must be the physical task for every decision point"
            )
        if len({item.cycle_id for item in points}) != len(points):
            raise PaperCapabilityEvaluationError("decision cycles must be unique")
        if self.capability_id == "POSITION_MANAGEMENT":
            identities = {
                (
                    item.account_id,
                    item.logical_agent_id,
                    item.physical_task_id,
                    item.agent_generation,
                    item.symbol,
                    item.episode_id,
                )
                for item in points
            }
            if len(identities) != 1:
                raise PaperCapabilityEvaluationError(
                    "position decisions must share one account, Agent and episode chain"
                )
            if len({item.transition_id for item in points}) != len(points):
                raise PaperCapabilityEvaluationError(
                    "position transitions must be unique"
                )
            if any(
                item.cycle_completion_status != "COMPLETE"
                for item in points[:-1]
            ) or points[-1].cycle_completion_status != "PRE_OUTCOME":
                raise PaperCapabilityEvaluationError(
                    "position evidence requires completed prior cycles and one pre-outcome current cycle"
                )
            mechanical = points[-1].position_mechanical_evidence
            if (
                mechanical is None
                or mechanical.d0_cycle_id != points[0].cycle_id
                or mechanical.d0_intent_sha256 != points[0].intent_sha256
                or any(
                    item.position_mechanical_evidence is not None
                    for item in points[:-1]
                )
            ):
                raise PaperCapabilityEvaluationError(
                    "position task requires exact D0 fill, D1 position and protective-stop facts"
                )
            for previous, current in zip(points, points[1:]):
                if not (
                    _time(previous.snapshot_sealed_at, field="snapshot_sealed_at")
                    < _time(current.snapshot_sealed_at, field="snapshot_sealed_at")
                    and _time(previous.decision_sealed_at, field="decision_sealed_at")
                    < _time(current.decision_sealed_at, field="decision_sealed_at")
                    and _time(previous.intent_authored_at, field="intent_authored_at")
                    < _time(current.intent_authored_at, field="intent_authored_at")
                ):
                    raise PaperCapabilityEvaluationError(
                        "position decisions must be fresh and strictly time ordered"
                    )
                if (
                    not current.prior_intent_sha256s
                    or current.prior_intent_sha256s[-1] != previous.intent_sha256
                ):
                    raise PaperCapabilityEvaluationError(
                        "each later paper context must expose the prior exact intent"
                    )
                if (
                    current.prior_decision_status != "PRIOR_COMPLETE_OBSERVED"
                    or current.prior_complete_cycle_id is None
                ):
                    raise PaperCapabilityEvaluationError(
                        "later paper context must bind the latest completed Review chain"
                    )
                if current.prior_complete_cycle_id == previous.cycle_id and (
                    current.prior_complete_intent_sha256
                    != previous.intent_sha256
                    or current.prior_complete_artifact_sha256s.get(
                        "HypothesisRecord"
                    )
                    != previous.hypothesis_record_sha256
                ):
                    raise PaperCapabilityEvaluationError(
                        "same-cycle completed Review must cross-bind the prior intent"
                    )
        if self.capability_id == "ATTENTION_SCHEDULING":
            identities = {
                (
                    item.account_id,
                    item.logical_agent_id,
                    item.physical_task_id,
                    item.agent_generation,
                    item.continuity_nonce,
                    item.symbol,
                )
                for item in points
            }
            if len(identities) != 1:
                raise PaperCapabilityEvaluationError(
                    "attention points must share one current physical and logical Agent"
                )
            for previous, current in zip(points, points[1:]):
                if not (
                    _time(previous.snapshot_sealed_at, field="snapshot_sealed_at")
                    < _time(current.snapshot_sealed_at, field="snapshot_sealed_at")
                    and _time(previous.followup_decision_at, field="followup_decision_at")
                    < _time(current.followup_decision_at, field="followup_decision_at")
                    and previous.attention_checkpoint_revision
                    < current.attention_checkpoint_revision
                ):
                    raise PaperCapabilityEvaluationError(
                        "attention checkpoint follow-ups must be fresh and time ordered"
                    )
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(
            self,
            "rubric",
            _verified_rubric(self.rubric, capability_id=self.capability_id),
        )
        object.__setattr__(self, "decision_points", points)

    @property
    def task_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": PAPER_CAPABILITY_SCHEMA_ID,
            "schema_version": PAPER_CAPABILITY_SCHEMA_VERSION,
            "document_type": "PRE_OUTCOME_PAPER_CAPABILITY_TASK",
            "task_id": self.task_id,
            "capability_id": self.capability_id,
            "policy_sha256": self.policy_sha256,
            "subject_agent_id": self.subject_agent_id,
            "assessor_id": self.assessor_id,
            "created_at": self.created_at,
            "assessment_due_at": self.assessment_due_at,
            "criteria": list(self.criteria),
            "rubric": _rubric_document(self.capability_id),
            "decision_points": [item.to_dict() for item in self.decision_points],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PreOutcomePaperCapabilityTaskV1":
        fields = frozenset(
            {
                "schema_id", "schema_version", "document_type", "task_id",
                "capability_id", "policy_sha256", "subject_agent_id", "assessor_id",
                "created_at", "assessment_due_at", "criteria", "rubric",
                "decision_points",
            }
        )
        document = _exact(
            value, fields=fields, document_type="PRE_OUTCOME_PAPER_CAPABILITY_TASK"
        )
        return cls(
            task_id=document["task_id"],
            capability_id=document["capability_id"],
            policy_sha256=document["policy_sha256"],
            subject_agent_id=document["subject_agent_id"],
            assessor_id=document["assessor_id"],
            created_at=document["created_at"],
            assessment_due_at=document["assessment_due_at"],
            criteria=_sequence(document["criteria"], field="criteria"),
            rubric=document["rubric"],
            decision_points=tuple(
                (
                    BoundAttentionSchedulingPointV1.from_dict(item)
                    if document["capability_id"] == "ATTENTION_SCHEDULING"
                    else BoundPaperDecisionPointV1.from_dict(item)
                )
                for item in _sequence(document["decision_points"], field="decision_points")
            ),
        )


def paper_capability_vector_for(
    findings: tuple[PaperCapabilityFindingV1, ...],
) -> Mapping[str, str]:
    if not findings or not all(
        isinstance(item, PaperCapabilityFindingV1) for item in findings
    ):
        raise PaperCapabilityEvaluationError(
            "paper capability vector requires explicit typed findings"
        )
    statuses = tuple(item.status for item in findings)
    capability = (
        "NOT_DEMONSTRATED_ON_THIS_SAMPLE"
        if "NOT_DEMONSTRATED" in statuses
        else "UNRESOLVED_ON_THIS_SAMPLE"
        if "UNRESOLVED" in statuses
        else "DEMONSTRATED_ON_THIS_SAMPLE"
    )
    return MappingProxyType(
        {
            "operational": "PRE_OUTCOME_PAPER_BINDINGS_VERIFIED",
            "capability": capability,
            "prediction": "NOT_EVALUATED_PRE_OUTCOME",
            "generalization": "NOT_EVALUATED_SINGLE_EPISODE",
            "profitability": "NOT_EVALUATED_NO_OUTCOME_COSTED_RETURN",
        }
    )


@dataclass(frozen=True, slots=True)
class PreOutcomePaperCapabilityAssessmentV1:
    """A no-total-score, pre-outcome paper capability judgment vector."""

    assessment_id: str
    task_id: str
    task_sha256: str
    capability_id: str
    policy_sha256: str
    subject_agent_id: str
    assessor_id: str
    assessed_at: str
    outcome_cutoff_at: str
    blindness_basis: str
    decision_point_sha256s: tuple[str, ...]
    findings: tuple[PaperCapabilityFindingV1, ...]
    assessment_vector: Mapping[str, str]
    limitations: tuple[str, ...]
    rubric: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in ("assessment_id", "task_id", "subject_agent_id", "assessor_id"):
            _identifier(getattr(self, field), field=field)
        if self.capability_id not in PAPER_CAPABILITY_IDS:
            raise PaperCapabilityEvaluationError("capability_id is unsupported")
        _sha256(self.task_sha256, field="task_sha256")
        _sha256(self.policy_sha256, field="policy_sha256")
        if self.subject_agent_id == self.assessor_id:
            raise PaperCapabilityEvaluationError(
                "assessor must be independent from the subject Agent identity"
            )
        if not is_physical_goal_identity(self.subject_agent_id):
            raise PaperCapabilityEvaluationError(
                "subject_agent_id must be a physical Codex Goal identity"
            )
        if not is_physical_goal_identity(self.assessor_id):
            raise PaperCapabilityEvaluationError(
                "assessor_id must be a physical Codex Goal identity"
            )
        if _time(self.assessed_at, field="assessed_at") >= _time(
            self.outcome_cutoff_at, field="outcome_cutoff_at"
        ):
            raise PaperCapabilityEvaluationError(
                "paper capability assessment must precede every Outcome"
            )
        if self.blindness_basis != PAPER_BLINDNESS_BASIS:
            raise PaperCapabilityEvaluationError("blindness_basis is invalid")
        point_hashes = tuple(self.decision_point_sha256s)
        if not point_hashes:
            raise PaperCapabilityEvaluationError("decision point bindings are required")
        for index, value in enumerate(point_hashes):
            _sha256(value, field=f"decision_point_sha256s[{index}]")
        findings = tuple(self.findings)
        if tuple(item.criterion_id for item in findings) != PAPER_CAPABILITY_CRITERIA[
            self.capability_id
        ]:
            raise PaperCapabilityEvaluationError(
                "findings are incomplete, duplicated or out of task order"
            )
        expected_vector = paper_capability_vector_for(findings)
        if (
            not isinstance(self.assessment_vector, Mapping)
            or tuple(self.assessment_vector) != PAPER_ASSESSMENT_VECTOR_KEYS
            or dict(self.assessment_vector) != dict(expected_vector)
        ):
            raise PaperCapabilityEvaluationError("assessment_vector is invalid")
        limitations = tuple(self.limitations)
        if not limitations or any(type(item) is not str or not item for item in limitations):
            raise PaperCapabilityEvaluationError("limitations must be non-empty text")
        object.__setattr__(self, "decision_point_sha256s", point_hashes)
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "assessment_vector", expected_vector)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(
            self,
            "rubric",
            _verified_rubric(self.rubric, capability_id=self.capability_id),
        )

    @property
    def assessment_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": PAPER_CAPABILITY_SCHEMA_ID,
            "schema_version": PAPER_CAPABILITY_SCHEMA_VERSION,
            "document_type": "PRE_OUTCOME_PAPER_CAPABILITY_ASSESSMENT",
            "assessment_id": self.assessment_id,
            "task_id": self.task_id,
            "task_sha256": self.task_sha256,
            "capability_id": self.capability_id,
            "policy_sha256": self.policy_sha256,
            "subject_agent_id": self.subject_agent_id,
            "assessor_id": self.assessor_id,
            "assessed_at": self.assessed_at,
            "outcome_cutoff_at": self.outcome_cutoff_at,
            "blindness_basis": self.blindness_basis,
            "decision_point_sha256s": list(self.decision_point_sha256s),
            "findings": [item.to_dict() for item in self.findings],
            "assessment_vector": dict(self.assessment_vector),
            "limitations": list(self.limitations),
            "rubric": _rubric_document(self.capability_id),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PreOutcomePaperCapabilityAssessmentV1":
        fields = frozenset(
            {
                "schema_id", "schema_version", "document_type", "assessment_id",
                "task_id", "task_sha256", "capability_id", "policy_sha256",
                "subject_agent_id", "assessor_id", "assessed_at", "outcome_cutoff_at",
                "blindness_basis", "decision_point_sha256s", "findings",
                "assessment_vector", "limitations", "rubric",
            }
        )
        document = _exact(
            value,
            fields=fields,
            document_type="PRE_OUTCOME_PAPER_CAPABILITY_ASSESSMENT",
        )
        vector = document["assessment_vector"]
        if not isinstance(vector, Mapping):
            raise PaperCapabilityEvaluationError("assessment_vector must be an object")
        return cls(
            assessment_id=document["assessment_id"],
            task_id=document["task_id"],
            task_sha256=document["task_sha256"],
            capability_id=document["capability_id"],
            policy_sha256=document["policy_sha256"],
            subject_agent_id=document["subject_agent_id"],
            assessor_id=document["assessor_id"],
            assessed_at=document["assessed_at"],
            outcome_cutoff_at=document["outcome_cutoff_at"],
            blindness_basis=document["blindness_basis"],
            decision_point_sha256s=_sequence(
                document["decision_point_sha256s"], field="decision_point_sha256s"
            ),
            findings=tuple(
                PaperCapabilityFindingV1.from_dict(item)
                for item in _sequence(document["findings"], field="findings")
            ),
            assessment_vector={
                key: vector[key] for key in PAPER_ASSESSMENT_VECTOR_KEYS if key in vector
            },
            limitations=_sequence(document["limitations"], field="limitations"),
            rubric=document["rubric"],
        )


__all__ = [
    "ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS",
    "BoundAttentionSchedulingPointV1",
    "BoundPaperDecisionPointV1",
    "PAPER_ASSESSMENT_VECTOR_KEYS",
    "PAPER_BLINDNESS_BASIS",
    "PAPER_CAPABILITY_CRITERIA",
    "PAPER_CAPABILITY_IDS",
    "PAPER_CAPABILITY_RUBRICS",
    "PAPER_CAPABILITY_SCHEMA_ID",
    "PAPER_CAPABILITY_SCHEMA_VERSION",
    "PAPER_EVIDENCE_SOURCE_KINDS",
    "PAPER_FINDING_STATUSES",
    "PaperCapabilityEvaluationError",
    "PaperCapabilityFindingV1",
    "PaperEvidenceSpanV1",
    "PositionMechanicalEvidenceV1",
    "PreOutcomePaperCapabilityAssessmentV1",
    "PreOutcomePaperCapabilityTaskV1",
    "paper_capability_vector_for",
]
