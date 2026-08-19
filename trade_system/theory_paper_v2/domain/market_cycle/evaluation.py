"""Read-only operational evaluation facts for V3.3.2.

This contract deliberately does not score an Agent, a market forecast, or a
position policy.  It binds already-sealed facts so a small operational run can
be replayed without turning endpoint movement or paper P&L into evidence of
predictive validity or profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_bytes, canonical_digest
from .contracts import ArtifactRef


class OperationalEvaluationContractError(ValueError):
    """One operational-evaluation binding is incomplete or inconsistent."""


OPERATIONAL_EVALUATION_DIMENSIONS = (
    "market_state",
    "direction",
    "path",
    "level",
    "timing",
    "mechanism",
    "action",
    "position",
    "transition",
    "risk",
    "churn",
    "reference_execution",
    "actual_execution",
    "attention_runtime",
)

_RUN_IDENTITY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "theory_manifest_sha256",
        "implementation_sha256",
        "contract_identity",
        "market_contract_identity",
        "experiment_identity",
        "run_manifest_identity_sha256",
    }
)
_POLICY_BINDING_FIELDS = frozenset({"document", "sha256"})
_ENDPOINT_MEASURE_FIELDS = frozenset(
    {
        "status",
        "unit",
        "decision_mark",
        "endpoint_mark",
        "absolute_change",
        "relative_change",
        "change_sign",
        "typed_missing",
    }
)
_ARTIFACT_TYPES = (
    "InputSnapshot",
    "HypothesisRecord",
    "BehaviorPlan",
    "Outcome",
    "Review",
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-/]{0,255}")


def _identifier(value: object, *, field: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise OperationalEvaluationContractError(f"{field} must be a safe identifier")
    return value


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise OperationalEvaluationContractError(f"{field} must be a SHA-256 digest")
    return value


def _timestamp(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        raise OperationalEvaluationContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationalEvaluationContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationalEvaluationContractError(f"{field} must include an offset")
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _freeze(value: object, *, field: str) -> Any:
    try:
        canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise OperationalEvaluationContractError(f"{field} must be canonical JSON") from exc
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item, field=field) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item, field=field) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class FrozenFactHeadV1:
    """One verified immutable prefix of a paper or attention journal."""

    owner_kind: str
    owner_id: str
    revision: int
    head_sha256: str
    bound_cycle_id: str

    def __post_init__(self) -> None:
        if self.owner_kind not in {"PAPER_LEDGER", "ATTENTION_JOURNAL"}:
            raise OperationalEvaluationContractError("owner_kind is unsupported")
        _identifier(self.owner_id, field="owner_id")
        if type(self.revision) is not int or self.revision < 1:
            raise OperationalEvaluationContractError("revision must be >= 1")
        _sha256(self.head_sha256, field="head_sha256")
        _identifier(self.bound_cycle_id, field="bound_cycle_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "revision": self.revision,
            "head_sha256": self.head_sha256,
            "bound_cycle_id": self.bound_cycle_id,
        }


@dataclass(frozen=True, slots=True)
class OperationalEvaluationFactsV1:
    """Content-addressed derived facts; never an effectiveness score."""

    evaluation_id: str
    evaluated_at: str
    run_identity: Mapping[str, Any]
    policy_binding: Mapping[str, Any]
    cycle_id: str
    artifact_refs: tuple[ArtifactRef, ...]
    input_raw_refs: tuple[ArtifactRef, ...]
    outcome_raw_refs: tuple[ArtifactRef, ...]
    endpoint_measure: Mapping[str, Any]
    paper_head: FrozenFactHeadV1 | None
    attention_head: FrozenFactHeadV1 | None
    paper_facts: Mapping[str, Any]
    attention_facts: Mapping[str, Any]
    dimension_statuses: Mapping[str, str]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.evaluation_id, field="evaluation_id")
        _timestamp(self.evaluated_at, field="evaluated_at")
        _identifier(self.cycle_id, field="cycle_id")

        if not isinstance(self.run_identity, Mapping) or frozenset(
            self.run_identity
        ) != _RUN_IDENTITY_FIELDS:
            raise OperationalEvaluationContractError("run_identity fields mismatch")
        run_identity = dict(self.run_identity)
        supplied_run_digest = _sha256(
            run_identity.pop("run_manifest_identity_sha256"),
            field="run_manifest_identity_sha256",
        )
        for field in ("theory_manifest_sha256", "implementation_sha256"):
            _sha256(run_identity[field], field=field)
        _identifier(run_identity["run_id"], field="run_id")
        for field in ("contract_identity", "market_contract_identity", "experiment_identity"):
            if type(run_identity[field]) is not str or not run_identity[field].strip():
                raise OperationalEvaluationContractError(f"{field} must be non-empty")
        if canonical_digest(run_identity) != supplied_run_digest:
            raise OperationalEvaluationContractError("run identity digest mismatch")

        if not isinstance(self.policy_binding, Mapping) or frozenset(
            self.policy_binding
        ) != _POLICY_BINDING_FIELDS:
            raise OperationalEvaluationContractError("policy_binding fields mismatch")
        policy_document = self.policy_binding["document"]
        if not isinstance(policy_document, Mapping):
            raise OperationalEvaluationContractError("policy document must be an object")
        if not isinstance(policy_document.get("policy_id"), str) or not isinstance(
            policy_document.get("theory_revision"), str
        ):
            raise OperationalEvaluationContractError("policy identity is incomplete")
        if canonical_digest(policy_document) != _sha256(
            self.policy_binding["sha256"], field="policy_binding.sha256"
        ):
            raise OperationalEvaluationContractError("policy digest mismatch")

        artifact_refs = tuple(self.artifact_refs)
        if not all(isinstance(ref, ArtifactRef) for ref in artifact_refs):
            raise OperationalEvaluationContractError("artifact_refs must contain ArtifactRef")
        if tuple(ref.artifact_type for ref in artifact_refs) != _ARTIFACT_TYPES:
            raise OperationalEvaluationContractError("artifact chain is incomplete or unordered")
        input_raw_refs = tuple(self.input_raw_refs)
        outcome_raw_refs = tuple(self.outcome_raw_refs)
        if not input_raw_refs or not all(isinstance(ref, ArtifactRef) for ref in input_raw_refs):
            raise OperationalEvaluationContractError("input_raw_refs must bind sealed raw")
        if not all(isinstance(ref, ArtifactRef) for ref in outcome_raw_refs):
            raise OperationalEvaluationContractError("outcome_raw_refs must contain ArtifactRef")

        if not isinstance(self.endpoint_measure, Mapping) or frozenset(
            self.endpoint_measure
        ) != _ENDPOINT_MEASURE_FIELDS:
            raise OperationalEvaluationContractError("endpoint_measure fields mismatch")
        endpoint = self.endpoint_measure
        if endpoint["status"] == "OBSERVED":
            if any(
                endpoint[field] is None
                for field in (
                    "unit",
                    "decision_mark",
                    "endpoint_mark",
                    "absolute_change",
                    "relative_change",
                    "change_sign",
                )
            ) or endpoint["typed_missing"] is not None:
                raise OperationalEvaluationContractError("observed endpoint facts are incomplete")
            if endpoint["change_sign"] not in {"UP", "DOWN", "FLAT"}:
                raise OperationalEvaluationContractError("change_sign is unsupported")
        elif endpoint["status"] == "TYPED_MISSING":
            if endpoint["typed_missing"] is None or any(
                endpoint[field] is not None
                for field in (
                    "endpoint_mark",
                    "absolute_change",
                    "relative_change",
                    "change_sign",
                )
            ):
                raise OperationalEvaluationContractError("typed-missing endpoint invented a value")
        else:
            raise OperationalEvaluationContractError("endpoint status is unsupported")

        if self.paper_head is not None:
            if self.paper_head.owner_kind != "PAPER_LEDGER" or self.paper_head.bound_cycle_id != self.cycle_id:
                raise OperationalEvaluationContractError("paper head cycle binding mismatch")
        if self.attention_head is not None:
            if self.attention_head.owner_kind != "ATTENTION_JOURNAL" or self.attention_head.bound_cycle_id != self.cycle_id:
                raise OperationalEvaluationContractError("attention head cycle binding mismatch")

        if not isinstance(self.dimension_statuses, Mapping) or tuple(
            self.dimension_statuses
        ) != OPERATIONAL_EVALUATION_DIMENSIONS:
            raise OperationalEvaluationContractError("dimension status set or order mismatch")
        for dimension, status in self.dimension_statuses.items():
            if type(status) is not str or not status:
                raise OperationalEvaluationContractError(
                    f"dimension {dimension} status must be non-empty"
                )
        limitations = tuple(self.limitations)
        if not limitations or any(type(item) is not str or not item.strip() for item in limitations):
            raise OperationalEvaluationContractError("limitations must remain explicit")

        object.__setattr__(self, "run_identity", _freeze(self.run_identity, field="run_identity"))
        object.__setattr__(self, "policy_binding", _freeze(self.policy_binding, field="policy_binding"))
        object.__setattr__(self, "artifact_refs", artifact_refs)
        object.__setattr__(self, "input_raw_refs", input_raw_refs)
        object.__setattr__(self, "outcome_raw_refs", outcome_raw_refs)
        object.__setattr__(self, "endpoint_measure", _freeze(endpoint, field="endpoint_measure"))
        object.__setattr__(self, "paper_facts", _freeze(self.paper_facts, field="paper_facts"))
        object.__setattr__(self, "attention_facts", _freeze(self.attention_facts, field="attention_facts"))
        object.__setattr__(self, "dimension_statuses", MappingProxyType(dict(self.dimension_statuses)))
        object.__setattr__(self, "limitations", limitations)

    def payload_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
            "evaluation_kind": "OPERATIONAL_FACTS_ONLY_NO_SCORE",
            "run_identity": _plain(self.run_identity),
            "policy_binding": _plain(self.policy_binding),
            "cycle_id": self.cycle_id,
            "artifact_refs": [ref.to_dict() for ref in self.artifact_refs],
            "input_raw_refs": [ref.to_dict() for ref in self.input_raw_refs],
            "outcome_raw_refs": [ref.to_dict() for ref in self.outcome_raw_refs],
            "endpoint_measure": _plain(self.endpoint_measure),
            "paper_head": None if self.paper_head is None else self.paper_head.to_dict(),
            "attention_head": None if self.attention_head is None else self.attention_head.to_dict(),
            "paper_facts": _plain(self.paper_facts),
            "attention_facts": _plain(self.attention_facts),
            "dimension_statuses": dict(self.dimension_statuses),
            "limitations": list(self.limitations),
        }

    @property
    def payload_sha256(self) -> str:
        return canonical_digest(self.payload_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.v332-operational-evaluation-facts",
            "schema_version": "1.0.0",
            "payload": self.payload_dict(),
            "payload_sha256": self.payload_sha256,
        }


__all__ = [
    "FrozenFactHeadV1",
    "OPERATIONAL_EVALUATION_DIMENSIONS",
    "OperationalEvaluationContractError",
    "OperationalEvaluationFactsV1",
]
