"""Local deterministic adapters for the four-cycle continuous-core fixture.

These adapters intentionally use synthetic observations.  They exercise the
same ports as a future collector and Strategy Agent without network, model,
account, order, or execution access.
"""

from __future__ import annotations

import hashlib
import fcntl
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.dynamic_research import MARKET_CATEGORIES, SENTIMENT_AXES
from ..domain.portfolio_truth import build_lot_position_truth
from ..domain.window_reliability import build_controller_reconciliation
from .research_cycle_store import ResearchCycleStore


class ContinuousFixtureInfrastructureError(ValueError):
    pass


class LocalControllerStateRepository:
    """Persist idempotent local controller receipts and the latest observation."""

    def __init__(self, run_root: Path) -> None:
        self.root = Path(run_root).resolve() / "controller"

    def persist(self, reconciliation: Mapping[str, Any]) -> Mapping[str, Any]:
        document = dict(reconciliation)
        try:
            verify_self_digest(document, "controller_reconciliation_digest")
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CONTROLLER_RECEIPT_INVALID"
            ) from exc
        idempotency_key = str(document.get("idempotency_key") or "")
        if len(idempotency_key) != 64:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CONTROLLER_IDEMPOTENCY_KEY_INVALID"
            )
        write_once_json(
            self.root / "commands" / f"{idempotency_key}.json",
            document,
        )
        _atomic_json(self.root / "current.json", document)
        return document


class LocalRunLease:
    """Process-held exclusive lease for one local synthetic run."""

    def __init__(self, run_root: Path, *, run_id: str) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_id = run_id
        self.controller_id = f"local-fixture:{run_id}"
        self.lease_id = f"lease:{uuid.uuid4()}"
        self.command_id = f"run:{uuid.uuid4()}"
        self._handle: Any = None
        self.states = LocalControllerStateRepository(self.run_root)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def __enter__(self) -> "LocalRunLease":
        lock_path = self.run_root / "controller" / "run.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CONTROLLER_LEASE_ALREADY_HELD"
            ) from exc
        self._handle = handle
        observed = datetime.now(UTC)
        try:
            self.states.persist(
                build_controller_reconciliation(
                    controller_id=self.controller_id,
                    command_id=self.command_id,
                    observed_at=self._iso(observed),
                    desired_state="RUNNING",
                    actual_state="ACTIVE",
                    lease_id=self.lease_id,
                    lease_expires_at=self._iso(observed + timedelta(minutes=5)),
                    kill_switch_engaged=False,
                )
            )
        except Exception:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            self._handle = None
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            observed = datetime.now(UTC)
            self.states.persist(
                build_controller_reconciliation(
                    controller_id=self.controller_id,
                    command_id=f"pause:{self.command_id}",
                    observed_at=self._iso(observed),
                    desired_state="PAUSED",
                    actual_state="PAUSED",
                    lease_id=None,
                    lease_expires_at=None,
                    kill_switch_engaged=True,
                )
            )
        finally:
            if self._handle is not None:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
                self._handle.close()
                self._handle = None


class CanonicalContinuousArtifactRepository:
    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str | None,
    ) -> Mapping[str, str]:
        if Path(relative_ref).is_absolute():
            raise ContinuousFixtureInfrastructureError("FIXTURE_ARTIFACT_REF_INVALID")
        path = (self.run_root / relative_ref).resolve()
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError("FIXTURE_ARTIFACT_REF_INVALID") from exc
        payload = dict(document)
        if digest_field is not None:
            payload = self_digest(payload, digest_field)
            semantic_digest = payload[digest_field]
        else:
            semantic_digest = ""
        write_once_json(path, payload)
        physical_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "relative_ref": relative_ref,
            "semantic_digest": semantic_digest or physical_sha256,
            "physical_sha256": physical_sha256,
        }

    def checkpoint_path(self) -> Path:
        return self.run_root / "checkpoint.json"

    def document_exists(self, *, relative_ref: str) -> bool:
        if Path(relative_ref).is_absolute():
            raise ContinuousFixtureInfrastructureError("FIXTURE_ARTIFACT_REF_INVALID")
        path = (self.run_root / relative_ref).resolve()
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_ARTIFACT_REF_INVALID"
            ) from exc
        return path.is_file()

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        from ..domain.contracts.canonical import load_json_strict

        if Path(relative_ref).is_absolute():
            raise ContinuousFixtureInfrastructureError("FIXTURE_ARTIFACT_REF_INVALID")
        path = (self.run_root / relative_ref).resolve()
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_ARTIFACT_REF_INVALID"
            ) from exc
        document = load_json_strict(path)
        try:
            semantic_digest = verify_self_digest(document, digest_field)
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_ARTIFACT_DIGEST_INVALID"
            ) from exc
        if (
            expected_semantic_digest is not None
            and semantic_digest != expected_semantic_digest
        ):
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_ARTIFACT_DIGEST_MISMATCH"
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
        path = (self.run_root / relative_ref).resolve()
        return {
            "relative_ref": relative_ref,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LocalContinuousCheckpointRepository:
    def __init__(self, run_root: Path) -> None:
        self.path = Path(run_root).resolve() / "checkpoint.json"

    def initialize(self, *, run_id: str) -> Mapping[str, Any]:
        document = self_digest({
            "schema_id": "synthetic_continuous_checkpoint",
            "schema_version": "1.1.0",
            "run_id": run_id,
            "status": "READY_FOR_CYCLE",
            "completed_cycles": 0,
            "next_cycle_index": 1,
            "accepted_state_path": None,
            "accepted_state_digest": None,
            "failure_count": 0,
            "last_failure_ref": None,
            "last_failure_digest": None,
            "last_failure_resume_allowed": None,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }, "checkpoint_digest")
        write_once_json(self.path, document)
        return document

    def load(self, *, run_id: str) -> Mapping[str, Any]:
        from ..domain.contracts.canonical import load_json_strict

        checkpoint = load_json_strict(self.path)
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        if checkpoint.get("run_id") != run_id:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CHECKPOINT_RUN_MISMATCH"
            )
        return checkpoint

    def binding(self, *, run_id: str) -> Mapping[str, str]:
        checkpoint = self.load(run_id=run_id)
        return {
            "relative_ref": "checkpoint.json",
            "semantic_digest": str(checkpoint["checkpoint_digest"]),
            "physical_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
        }

    def record_failure(
        self,
        *,
        run_id: str,
        cycle_index: int,
        failure_ref: str,
        failure_digest: str,
        resume_allowed: bool,
        accepted_state_exists: bool,
    ) -> Mapping[str, Any]:
        checkpoint = dict(self.load(run_id=run_id))
        allowed_statuses = (
            {
                "POST_ACCEPT_FINALIZATION",
                "POST_ACCEPT_RECOVERABLE_FAILURE",
            }
            if accepted_state_exists
            else {
                "READY_FOR_CYCLE",
                "RUNNING_OUTCOMES_SEALED",
                "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
                "PRE_ACCEPT_RECOVERABLE_FAILURE",
            }
        )
        if (
            checkpoint.get("next_cycle_index") != cycle_index
            or checkpoint.get("completed_cycles") != cycle_index - 1
            or checkpoint.get("status") not in allowed_statuses
            or not isinstance(resume_allowed, bool)
            or not isinstance(accepted_state_exists, bool)
            or not failure_ref
            or not isinstance(failure_digest, str)
            or len(failure_digest) != 64
        ):
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_FAILURE_CHECKPOINT_INVALID"
            )
        updated = dict(checkpoint)
        updated.update(
            {
                "status": (
                    "POST_ACCEPT_RECOVERABLE_FAILURE"
                    if accepted_state_exists and resume_allowed
                    else "POST_ACCEPT_FAILED_CLOSED"
                    if accepted_state_exists
                    else "PRE_ACCEPT_RECOVERABLE_FAILURE"
                    if resume_allowed
                    else "PRE_ACCEPT_FAILED_CLOSED"
                ),
                "last_failure_ref": failure_ref,
                "last_failure_digest": failure_digest,
                "last_failure_resume_allowed": resume_allowed,
                "failure_count": int(checkpoint.get("failure_count", 0)) + 1,
            }
        )
        updated = self_digest(updated, "checkpoint_digest")
        _atomic_json(self.path, updated)
        return updated

    def open_cycle(self, *, run_id: str, cycle_index: int) -> Mapping[str, Any]:
        from ..domain.contracts.canonical import load_json_strict

        checkpoint = load_json_strict(self.path)
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        if (
            checkpoint.get("run_id") != run_id
            or checkpoint.get("next_cycle_index") != cycle_index
            or checkpoint.get("completed_cycles") != cycle_index - 1
            or checkpoint.get("status")
            not in {
                "READY_FOR_CYCLE",
                "RUNNING_OUTCOMES_SEALED",
                "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
                "PRE_ACCEPT_RECOVERABLE_FAILURE",
                "POST_ACCEPT_FINALIZATION",
                "POST_ACCEPT_RECOVERABLE_FAILURE",
            }
        ):
            raise ContinuousFixtureInfrastructureError("FIXTURE_CHECKPOINT_OPEN_INVALID")
        # The verified write-once event chain is the in-cycle cursor.  Avoiding
        # an open-only checkpoint mutation keeps the origin capsule digest valid.
        return checkpoint


class LocalResearchCycleStoreFactory:
    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()

    def open_cycle(self, *, run_id: str, cycle_index: int) -> ResearchCycleStore:
        return ResearchCycleStore(self.run_root, run_id=run_id, cycle_index=cycle_index)


class SyntheticMarketCollector:
    """Create ten-category facts and real local raw artifacts."""

    def __init__(self, artifacts: CanonicalContinuousArtifactRepository) -> None:
        self.artifacts = artifacts

    def collect(
        self, *, run_id: str, cycle_index: int, as_of: str
    ) -> Mapping[str, Any]:
        facts: list[dict[str, Any]] = []
        raw_bindings: dict[str, Mapping[str, str]] = {}
        for index, category in enumerate(MARKET_CATEGORIES):
            unavailable = (
                category == "LIQUIDATION" and cycle_index < 3
            ) or (
                category == "NEWS_EVENTS_AND_REACTION" and cycle_index == 1
            )
            raw_ref = f"raw/cycle-{cycle_index:04d}/{category.lower()}.json"
            raw_binding = self.artifacts.write_document(
                relative_ref=raw_ref,
                document={
                    "schema_id": "synthetic_market_observation_or_attempt",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "category": category,
                    "status": "UNAVAILABLE" if unavailable else "OBSERVED",
                    "value": None if unavailable else str(100 + cycle_index * 10 + index),
                    "as_of": as_of,
                    "synthetic": True,
                },
                digest_field="raw_observation_digest",
            )
            raw_bindings[category] = raw_binding
            facts.append(
                {
                    "fact_id": f"fact:c{cycle_index}:{index}",
                    "kind": "RAW_FACT",
                    "category": category,
                    "metric": f"synthetic_{category.lower()}",
                    "value": None if unavailable else str(100 + cycle_index * 10 + index),
                    "unit": "SYNTHETIC_INDEX",
                    "symbol": "SYNTHUSDT",
                    "timeframe": "1h",
                    "window": f"cycle-{cycle_index:04d}-closed-window",
                    "source_ref": f"fixture://{category.lower()}",
                    "raw_ref": raw_ref,
                    "raw_sha256": None if unavailable else raw_binding["physical_sha256"],
                    "observed_at": as_of,
                    "available_at": as_of,
                    "quality": "UNKNOWN" if unavailable else "GOOD",
                    "coverage": "0" if unavailable else "1",
                    "dependency_group": f"dependency:{category.lower()}",
                    "lineage": [],
                    "transform": None,
                    "limitations": "synthetic chronology; no market validity claim",
                    "missing_reason": "SYNTHETIC_SOURCE_UNAVAILABLE" if unavailable else None,
                }
            )
        price_raw = facts[0]
        facts.append(
            {
                "fact_id": f"fact:c{cycle_index}:10",
                "kind": "DERIVED_FEATURE",
                "category": "PRICE_AND_RETURNS",
                "metric": "synthetic_closed_window_return",
                "value": str(cycle_index),
                "unit": "SYNTHETIC_PERCENT",
                "symbol": "SYNTHUSDT",
                "timeframe": "1h",
                "window": f"cycle-{cycle_index:04d}-closed-window",
                "source_ref": "fixture://deterministic-return-transform",
                "raw_ref": price_raw["raw_ref"],
                "raw_sha256": raw_bindings["PRICE_AND_RETURNS"]["physical_sha256"],
                "observed_at": as_of,
                "available_at": as_of,
                "quality": "GOOD",
                "coverage": "1",
                "dependency_group": price_raw["dependency_group"],
                "lineage": [price_raw["fact_id"]],
                "transform": "current synthetic close minus prior synthetic close",
                "limitations": "synthetic derived feature; no market validity claim",
                "missing_reason": None,
            }
        )
        return {
            "facts": facts,
            "attempt_count": len(MARKET_CATEGORIES),
            "observed_count": sum(
                row["kind"] == "RAW_FACT" and row["value"] is not None
                for row in facts
            ),
            "unknown_count": sum(
                row["kind"] == "RAW_FACT" and row["value"] is None
                for row in facts
            ),
            "derived_feature_count": sum(
                row["kind"] == "DERIVED_FEATURE" for row in facts
            ),
            "collector_id": "SYNTHETIC_TEN_CATEGORY_COLLECTOR_V1",
        }


def _hypothesis(
    hypothesis_id: str,
    *,
    family: str,
    created_at: str,
    state: str = "ACTIVE",
    revision: int = 1,
    parents: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    evidence_bindings: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    parent_ids = parents or []
    active_evidence_ids = evidence_ids or []
    active_evidence_bindings = dict(evidence_bindings or {})
    if set(active_evidence_bindings) != set(active_evidence_ids):
        raise ContinuousFixtureInfrastructureError(
            "FIXTURE_HYPOTHESIS_EVIDENCE_BINDING_INVALID"
        )
    return {
        "hypothesis_id": hypothesis_id,
        "revision": revision,
        "hypothesis_type": "PATH",
        "directional_bias": "BIDIRECTIONAL",
        "family_label": family,
        "deduplication_key": f"semantic:{family}",
        "state": state,
        "parent_hypothesis_ids": parent_ids,
        "supersedes_ids": parent_ids,
        "derived_from_expectation_ids": [],
        "created_at": created_at,
        "updated_at": created_at,
        "horizon": "next four closed synthetic 1h bars",
        "timeframe_scope": ["4h", "1h"],
        "premises": ["registered synthetic structure remains observable"],
        "expected_sequence": ["liquidity test", "closed-bar response", "persistence check"],
        "support_rules": ["registered response sequence is observed"],
        "oppose_rules": ["registered response fails to persist"],
        "hard_falsifiers": [f"hard-falsifier:{hypothesis_id}"],
        "expiry": "2026-08-07T12:00:00Z",
        "trade_triggers": [],
        "forbidden_conditions": ["data coverage below the registered threshold"],
        "active_evidence_ids": active_evidence_ids,
        "active_evidence_bindings": active_evidence_bindings,
        "support_level": "PLAUSIBLE",
        "limitations": ["synthetic fixture only"],
        "novelty_reason": "mechanism has a distinct causal sequence and discriminator",
        "agent_rationale": "keep as a competing process until its registered discriminator resolves",
    }


def _hypothesis_delta(
    delta_id: str,
    operation: str,
    *,
    at: str,
    targets: list[str],
    replacements: list[Mapping[str, Any]],
    evidence_ids: list[str],
    evidence_bindings: Mapping[str, str],
) -> dict[str, Any]:
    if set(evidence_bindings) != set(evidence_ids):
        raise ContinuousFixtureInfrastructureError(
            "FIXTURE_HYPOTHESIS_DELTA_EVIDENCE_BINDING_INVALID"
        )
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_hypothesis_ids": targets,
        "replacement_hypotheses": [dict(row) for row in replacements],
        "evidence_ids": evidence_ids,
        "evidence_bindings": dict(evidence_bindings),
        "matched_hard_falsifier": None,
        "agent_rationale": "synthetic evidence changes the competitive mechanism set",
    }


def _expectation(
    expectation_id: str,
    *,
    hypothesis_id: str,
    revision: int,
    status: str,
    created_at: str,
    updated_at: str,
    deadline: str,
    result_refs: list[str] | None = None,
    result_bindings: Mapping[str, str] | None = None,
    closed_at: str | None = None,
) -> dict[str, Any]:
    result_evidence_refs = result_refs or []
    result_evidence_bindings = dict(result_bindings or {})
    if set(result_evidence_bindings) != set(result_evidence_refs):
        raise ContinuousFixtureInfrastructureError(
            "FIXTURE_EXPECTATION_EVIDENCE_BINDING_INVALID"
        )
    return {
        "expectation_id": expectation_id,
        "revision": revision,
        "hypothesis_id": hypothesis_id,
        "parent_expectation_id": None,
        "deduplication_key": f"semantic:{expectation_id}:window:{deadline}",
        "created_at": created_at,
        "updated_at": updated_at,
        "observation_start": created_at,
        "observation_deadline": deadline,
        "if_conditions": ["synthetic support remains intact"],
        "expected_observations": [
            {
                "metric": "synthetic_price_and_returns",
                "direction_or_range": "higher than the prior closed window",
                "timeframe": "1h",
                "source_requirement": "closed synthetic observation",
            }
        ],
        "falsifying_observations": [
            {
                "metric": "synthetic_price_and_returns",
                "direction_or_range": "below registered invalidation",
                "timeframe": "1h",
                "source_requirement": "closed synthetic observation",
            }
        ],
        "evidence_sufficiency": "LOW" if status == "OPEN" else "MEDIUM",
        "status": status,
        "result_evidence_refs": result_evidence_refs,
        "result_evidence_bindings": result_evidence_bindings,
        "closed_at": closed_at,
        "result_note": (
            "synthetic observation fulfilled the registered sequence"
            if closed_at
            else "partial synthetic observation recorded"
            if status == "PARTIAL"
            else None
        ),
    }


def _expectation_delta(
    delta_id: str,
    operation: str,
    *,
    at: str,
    target: str | None,
    expectation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_expectation_id": target,
        "expectation": dict(expectation),
        "agent_rationale": "compare the registered expectation with current admitted facts",
    }


def _candidate_rows(
    *,
    cycle_index: int,
    lead: str,
    runner: str,
    residual: str,
    position_truth_digest: str,
) -> list[dict[str, Any]]:
    specifications = (
        ("hold", "HOLD", "HOLD_CURRENT", "0", None),
        ("open", "OPEN", "OPEN_PROBE", "0.1", "90"),
        ("add", "ADD", "ADD_PROBE", "0.1", "90"),
        ("reduce25", "REDUCE", "REDUCE_25", "-0.25", "90"),
        ("reduce50", "REDUCE", "REDUCE_50", "-0.5", "90"),
        ("reduce75", "REDUCE", "REDUCE_75", "-0.75", "90"),
        ("partial", "PARTIAL_TAKE_PROFIT", "PARTIAL_25", "-0.25", "90"),
        ("exit", "EXIT", "EXIT_100", "-1", None),
        ("reenter", "REENTER", "REENTER_PROBE", "0.1", "90"),
        ("wait", "WAIT", "WAIT_REVIEW", "0", None),
    )
    rows: list[dict[str, Any]] = []
    for suffix, action_class, sizing_id, delta, stop in specifications:
        candidate_id = f"candidate:c{cycle_index}:{suffix}"
        path_outcomes = []
        for path_id, label in ((lead, "lead"), (runner, "runner"), (residual, "residual")):
            path_outcomes.append(
                {
                    "path_id": path_id,
                    "source_cycle_index": cycle_index,
                    "position_truth_digest": position_truth_digest,
                    "process_id": f"process:c{cycle_index}:{suffix}:{label}",
                    "distinguishing_evidence_refs": [f"fact:c{cycle_index}:0"],
                    "failure_trigger_refs": [f"trigger:{path_id}"],
                    "position_consequence": f"{action_class} changes exposure under {label}",
                    "compatibility": f"{label.upper()}_PATH_CONDITIONAL",
                    "market_process": f"registered {label} mechanism unfolds through closed synthetic observations",
                    "failure_process": f"registered {label} discriminator fails",
                    "opportunity_cost": "both action and inaction retain explicit opportunity cost",
                    "cost_risk_tradeoff": "lot quantity, stop, fee, margin, and leverage are recomputed",
                }
            )
        rows.append(
            {
                "candidate_id": candidate_id,
                "source_cycle_index": cycle_index,
                "action_class": action_class,
                "sizing_id": sizing_id,
                "quantity_delta": delta,
                "stop_price_after": (
                    None if action_class in {"HOLD", "WAIT", "EXIT"} else stop
                ),
                "target_lot_ids": (
                    [] if action_class in {"OPEN", "REENTER"} else ["lot:SYNTHUSDT:core"]
                ),
                "target_lot_role": "CORE",
                "thesis_path_id": lead,
                "evidence_refs": [f"fact:c{cycle_index}:0"],
                "rationale": f"compare {action_class} against the same three process paths",
                "path_outcomes": path_outcomes,
                "wait_until": f"2026-08-06T0{cycle_index + 1}:30:00Z" if action_class == "WAIT" else None,
                "wait_for_observations": [f"fact:c{cycle_index + 1}:0"] if action_class == "WAIT" else [],
            }
        )
    return rows


def _public_inference_claims(
    *,
    cycle_index: int,
    lead: str,
    mechanism_target: str,
    expectation_id: str,
    expectation_effect: str,
    hypothesis_effect: str,
    market_snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Emit public evidence-linked conclusions, never private chain-of-thought."""

    fact_by_id = {row["fact_id"]: row for row in market_snapshot["facts"]}
    unknown_ids = sorted(
        fact_id for fact_id, row in fact_by_id.items() if row["value"] is None
    )
    valid_until = f"2026-08-06T0{cycle_index + 1}:00:00Z"
    return [
        {
            "claim_id": f"inference:c{cycle_index}:state",
            "claim_type": "STATE_INFERENCE",
            "statement": (
                "Closed synthetic price and participation observations support a "
                "conditional state, while leverage-positioning evidence preserves "
                "a competing interpretation."
            ),
            "epistemic_status": "CONTESTED",
            "directional_bias": "BIDIRECTIONAL",
            "timeframe_scope": ["4h", "1h"],
            "supporting_fact_ids": [
                f"fact:c{cycle_index}:10",
                f"fact:c{cycle_index}:2",
            ],
            "contradicting_fact_ids": [f"fact:c{cycle_index}:5"],
            "unknown_fact_ids": unknown_ids,
            "prior_claim_ids": [],
            "financial_mechanism": (
                "Price response and active participation can sustain exposure, but "
                "funding and open-interest proxies cannot identify trader identity or "
                "true open-close roles and therefore cannot settle direction alone."
            ),
            "hypothesis_effects": [
                {
                    "hypothesis_id": lead,
                    "effect": "SUPPORT",
                    "rationale": "the admitted closed-window prefix remains compatible with the lead path",
                }
            ],
            "expectation_effects": [
                {
                    "expectation_id": expectation_id,
                    "effect": expectation_effect,
                    "rationale": "the expectation lifecycle follows only the registered closed observation",
                }
            ],
            "action_implications": [
                {
                    "action_class": "HOLD",
                    "effect": "CONDITIONAL",
                    "rationale": "retention remains conditional on stop-defined risk and the next discriminator",
                },
                {
                    "action_class": "WAIT",
                    "effect": "CONDITIONAL",
                    "rationale": "waiting has opportunity cost and must carry a next-review obligation",
                },
            ],
            "falsification_conditions": [
                "the registered closed-window response reverses beyond the hypothesis hard falsifier",
                "source quality falls below the admitted coverage boundary",
            ],
            "limitations": [
                "synthetic chronology has no real-market validity",
                "public leverage proxies do not reveal participant intent or true position roles",
            ],
            "next_discriminating_observations": [
                "next closed 1h price-and-flow response",
                "point-in-time liquidity response with unchanged source lineage",
            ],
            "valid_until": valid_until,
        },
        {
            "claim_id": f"inference:c{cycle_index}:mechanism",
            "claim_type": "MECHANISM_INFERENCE",
            "statement": (
                "A liquidity-response mechanism remains a distinct candidate rather "
                "than being collapsed into the fixed operational shortlist."
            ),
            "epistemic_status": "CONTESTED",
            "directional_bias": "BIDIRECTIONAL",
            "timeframe_scope": ["1h", "15m"],
            "supporting_fact_ids": [
                f"fact:c{cycle_index}:3",
                f"fact:c{cycle_index}:10",
            ],
            "contradicting_fact_ids": [f"fact:c{cycle_index}:4"],
            "unknown_fact_ids": unknown_ids,
            "prior_claim_ids": [f"inference:c{cycle_index}:state"],
            "financial_mechanism": (
                "Liquidity withdrawal can amplify price impact and later reversal, "
                "whereas rising open interest can also accompany continuation; the "
                "closed replenishment sequence must discriminate the mechanisms."
            ),
            "hypothesis_effects": [
                {
                    "hypothesis_id": mechanism_target,
                    "effect": hypothesis_effect,
                    "rationale": "the mechanism remains separately identifiable and falsifiable",
                }
            ],
            "expectation_effects": [
                {
                    "expectation_id": expectation_id,
                    "effect": "NO_CHANGE",
                    "rationale": "the mechanism claim does not silently overwrite the registered expectation result",
                }
            ],
            "action_implications": [
                {
                    "action_class": "ADD",
                    "effect": "CONDITIONAL",
                    "rationale": "adding requires deterministic lot, fee, margin, leverage and stop validation",
                },
                {
                    "action_class": "REDUCE",
                    "effect": "CONDITIONAL",
                    "rationale": "reduction must be compared with retained participation and re-entry delay",
                },
                {
                    "action_class": "EXIT",
                    "effect": "NO_CONCLUSION",
                    "rationale": "this evidence alone cannot justify permanent core exit",
                },
            ],
            "falsification_conditions": [
                "the registered liquidity sequence is absent on the next closed observation",
                "an independent source shows the apparent response was a data artifact",
            ],
            "limitations": [
                "one snapshot cannot prove strict executable liquidity resilience",
                "missing liquidation observations remain UNKNOWN rather than zero",
            ],
            "next_discriminating_observations": [
                "closed post-stress depth replenishment sequence",
                "independent liquidation observation with point-in-time availability",
            ],
            "valid_until": valid_until,
        },
    ]


class SyntheticStrategyAgent:
    """Fixed local adapter that emits open semantic proposals and later deliberates."""

    def __init__(self, artifacts: CanonicalContinuousArtifactRepository) -> None:
        self.artifacts = artifacts

    def _transport_ref(
        self,
        *,
        kind: str,
        cycle_index: int,
        input_digest: str,
    ) -> str:
        return (
            f"transport/cycle-{cycle_index:04d}/"
            f"{kind}-{input_digest}.json"
        )

    def _load_transport_delivery(
        self,
        *,
        kind: str,
        run_id: str,
        cycle_index: int,
        input_digest: str,
    ) -> Mapping[str, Any] | None:
        relative_ref = self._transport_ref(
            kind=kind,
            cycle_index=cycle_index,
            input_digest=input_digest,
        )
        if not self.artifacts.document_exists(relative_ref=relative_ref):
            return None
        record = self.artifacts.read_document(
            relative_ref=relative_ref,
            digest_field="transport_delivery_record_digest",
        )
        if (
            record.get("run_id") != run_id
            or record.get("cycle_index") != cycle_index
            or record.get("input_digest") != input_digest
            or record.get("delivery_kind") != kind
            or not isinstance(record.get("delivery"), Mapping)
        ):
            raise ContinuousFixtureInfrastructureError(
                "FIXTURE_TRANSPORT_DELIVERY_RECORD_INVALID"
            )
        binding = self.artifacts.artifact_binding(
            relative_ref=relative_ref,
            digest_field="transport_delivery_record_digest",
            expected_semantic_digest=str(
                record["transport_delivery_record_digest"]
            ),
        )
        return {
            **dict(record["delivery"]),
            "transport_record_ref": binding["relative_ref"],
            "transport_record_digest": binding["semantic_digest"],
            "transport_record_sha256": binding["physical_sha256"],
            "durable_before_adapter_return": True,
        }

    def _persist_transport_delivery(
        self,
        *,
        kind: str,
        run_id: str,
        cycle_index: int,
        input_digest: str,
        delivery: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        record = self_digest(
            {
                "schema_id": "synthetic_durable_transport_delivery",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "delivery_kind": kind,
                "input_digest": input_digest,
                "delivery": dict(delivery),
                "durable_before_adapter_return": True,
                "network_access": False,
                "model_invocation": False,
            },
            "transport_delivery_record_digest",
        )
        binding = self.artifacts.write_document(
            relative_ref=self._transport_ref(
                kind=kind,
                cycle_index=cycle_index,
                input_digest=input_digest,
            ),
            document=record,
            digest_field="transport_delivery_record_digest",
        )
        return {
            **dict(delivery),
            "transport_record_ref": binding["relative_ref"],
            "transport_record_digest": binding["semantic_digest"],
            "transport_record_sha256": binding["physical_sha256"],
            "durable_before_adapter_return": True,
        }

    @staticmethod
    def _complete_delivery(
        *,
        run_id: str,
        cycle_index: int,
        input_digest: str,
        expected_schema_id: str,
        payload: Mapping[str, Any],
        adapter_receipt_id: str,
    ) -> Mapping[str, Any]:
        document = dict(payload)
        return {
            "delivery_status": "COMPLETE",
            "finish_reason": "STOP",
            "truncated": False,
            "complete_json_object": True,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "input_digest": input_digest,
            "expected_schema_id": expected_schema_id,
            "payload": document,
            "payload_digest": canonical_digest(document),
            "payload_canonical_bytes": len(canonical_bytes(document)),
            "adapter_receipt_id": adapter_receipt_id,
        }

    def propose(self, *, context: Mapping[str, Any]) -> Mapping[str, Any]:
        cycle = int(context["cycle_index"])
        run_id = str(context["run_id"])
        input_digest = str(context["agent_context_digest"])
        recovered = self._load_transport_delivery(
            kind="proposal",
            run_id=run_id,
            cycle_index=cycle,
            input_digest=input_digest,
        )
        if recovered is not None:
            return recovered
        at = str(context["decision_at"])
        snapshot = context["market_information_snapshot"]
        fact_digest_by_id = {
            str(row["fact_id"]): canonical_digest(row)
            for row in snapshot["facts"]
        }

        def bindings_for(evidence_ids: list[str]) -> dict[str, str]:
            try:
                return {
                    evidence_id: fact_digest_by_id[evidence_id]
                    for evidence_id in evidence_ids
                }
            except KeyError as exc:
                raise ContinuousFixtureInfrastructureError(
                    "FIXTURE_EVIDENCE_REF_UNKNOWN"
                ) from exc

        facts_by_category: dict[str, list[Mapping[str, Any]]] = {}
        for row in snapshot["facts"]:
            facts_by_category.setdefault(row["category"], []).append(row)
        axis_categories = {
            "PRICE_DIRECTIONAL_PRESSURE": ("PRICE_AND_RETURNS",),
            "STRUCTURE_PERSISTENCE": ("TREND_VOLATILITY_AND_STRUCTURE",),
            "PARTICIPATION_AND_FLOW": ("VOLUME_AND_ACTIVE_FLOW",),
            "CROWDING_DIRECTION": ("FUNDING_BASIS_AND_POSITIONING",),
            "LEVERAGE_CHANGE": ("OPEN_INTEREST_AND_LEVERAGE", "LIQUIDATION"),
            "LIQUIDITY_RESILIENCE": ("ORDER_BOOK_AND_LIQUIDITY",),
            "VOLATILITY_STRESS": ("TREND_VOLATILITY_AND_STRUCTURE", "LIQUIDATION"),
            "CROSS_MARKET_RISK_APPETITE": ("CROSS_MARKET_AND_MACRO",),
            "EVENT_REACTION": ("NEWS_EVENTS_AND_REACTION",),
            "TIMEFRAME_COHERENCE": ("TREND_VOLATILITY_AND_STRUCTURE", "PRICE_AND_RETURNS"),
        }
        dimensions: list[dict[str, Any]] = []
        for axis in SENTIMENT_AXES:
            selected_facts = [
                facts_by_category[category][0]
                for category in axis_categories[axis]
            ]
            contribution = 1 if cycle < 3 else -1 if axis in {"LIQUIDITY_RESILIENCE", "EVENT_REACTION"} else 1
            dimensions.append(
                {
                    "axis": axis,
                    "required_dependency_groups": list(
                        dict.fromkeys(fact["dependency_group"] for fact in selected_facts)
                    ),
                    "contributors": [
                        {
                            "fact_id": fact["fact_id"],
                            "ordinal_contribution": contribution,
                            "rule": f"synthetic cycle {cycle} registered rule for {axis}",
                            "direction": "POSITIVE" if contribution > 0 else "NEGATIVE",
                        }
                        for fact in selected_facts
                        if fact["value"] is not None
                    ],
                    "timeframe_states": {
                        "1h": (
                            contribution
                            if any(fact["value"] is not None for fact in selected_facts)
                            else None
                        )
                    },
                    "agent_interpretation": f"cycle {cycle} interprets {axis} only from its bound fact",
                    "limitations": "synthetic fixture cannot establish real market sentiment validity",
                    "next_discriminating_observation": "next closed synthetic 1h observation",
                }
            )
        prior_view = context["previous_research_state_view"]
        previous_registry = prior_view.get("hypothesis_registry")
        hypothesis_deltas: list[dict[str, Any]] = []
        if cycle == 1:
            for suffix, family in (
                ("base", "structured-trend-continuation"),
                ("pullback", "normal-pullback-recovery"),
                ("residual", "other-or-unknown"),
            ):
                item = _hypothesis(
                    f"hypothesis:{suffix}",
                    family=family,
                    created_at=at,
                    evidence_ids=[f"fact:c{cycle}:0"],
                    evidence_bindings=bindings_for([f"fact:c{cycle}:0"]),
                )
                hypothesis_deltas.append(
                    _hypothesis_delta(
                        f"hypothesis-delta:c{cycle}:{suffix}",
                        "CREATE",
                        at=at,
                        targets=[],
                        replacements=[item],
                        evidence_ids=[f"fact:c{cycle}:0"],
                        evidence_bindings=bindings_for([f"fact:c{cycle}:0"]),
                    )
                )
        elif cycle == 2:
            novel = _hypothesis(
                "hypothesis:event-liquidity-vacuum-reversal",
                family="event-liquidity-vacuum-reversal",
                created_at=at,
                state="WATCH",
                evidence_ids=[f"fact:c{cycle}:8", f"fact:c{cycle}:3"],
                evidence_bindings=bindings_for(
                    [f"fact:c{cycle}:8", f"fact:c{cycle}:3"]
                ),
            )
            hypothesis_deltas.append(
                _hypothesis_delta(
                    "hypothesis-delta:c2:create-novel-direction",
                    "CREATE",
                    at=at,
                    targets=[],
                    replacements=[novel],
                    evidence_ids=[f"fact:c{cycle}:8", f"fact:c{cycle}:3"],
                    evidence_bindings=bindings_for(
                        [f"fact:c{cycle}:8", f"fact:c{cycle}:3"]
                    ),
                )
            )
        elif cycle == 3:
            by_id = {row["hypothesis_id"]: row for row in previous_registry["hypotheses"]}
            novel = {
                **by_id["hypothesis:event-liquidity-vacuum-reversal"],
                "revision": 2,
                "state": "ACTIVE",
                "updated_at": at,
                "active_evidence_ids": sorted(set(by_id["hypothesis:event-liquidity-vacuum-reversal"]["active_evidence_ids"]) | {f"fact:c{cycle}:6"}),
                "active_evidence_bindings": {
                    **by_id["hypothesis:event-liquidity-vacuum-reversal"][
                        "active_evidence_bindings"
                    ],
                    **bindings_for([f"fact:c{cycle}:6"]),
                },
                "agent_rationale": "observed synthetic liquidation makes the new mechanism operationally competitive",
            }
            pullback = {
                **by_id["hypothesis:pullback"],
                "revision": 2,
                "state": "DORMANT",
                "updated_at": at,
                "agent_rationale": "active budget now favors the new liquidity mechanism",
            }
            hypothesis_deltas.extend(
                [
                    _hypothesis_delta(
                        "hypothesis-delta:c3:promote-novel",
                        "PROMOTE",
                        at=at,
                        targets=[novel["hypothesis_id"]],
                        replacements=[novel],
                        evidence_ids=[f"fact:c{cycle}:6"],
                        evidence_bindings=bindings_for([f"fact:c{cycle}:6"]),
                    ),
                    _hypothesis_delta(
                        "hypothesis-delta:c3:demote-pullback",
                        "DEMOTE",
                        at=at,
                        targets=[pullback["hypothesis_id"]],
                        replacements=[pullback],
                        evidence_ids=[f"fact:c{cycle}:0"],
                        evidence_bindings=bindings_for([f"fact:c{cycle}:0"]),
                    ),
                ]
            )
        elif cycle == 4:
            by_id = {row["hypothesis_id"]: row for row in previous_registry["hypotheses"]}
            novel = {
                **by_id["hypothesis:event-liquidity-vacuum-reversal"],
                "revision": 3,
                "updated_at": at,
                "active_evidence_ids": sorted(set(by_id["hypothesis:event-liquidity-vacuum-reversal"]["active_evidence_ids"]) | {f"fact:c{cycle}:3"}),
                "active_evidence_bindings": {
                    **by_id["hypothesis:event-liquidity-vacuum-reversal"][
                        "active_evidence_bindings"
                    ],
                    **bindings_for([f"fact:c{cycle}:3"]),
                },
                "agent_rationale": "revise the mechanism with the latest synthetic liquidity response",
            }
            hypothesis_deltas.append(
                _hypothesis_delta(
                    "hypothesis-delta:c4:revise-novel",
                    "REVISE",
                    at=at,
                    targets=[novel["hypothesis_id"]],
                    replacements=[novel],
                    evidence_ids=[f"fact:c{cycle}:3"],
                    evidence_bindings=bindings_for([f"fact:c{cycle}:3"]),
                )
            )
        previous_ledger = prior_view.get("expectation_ledger")
        if cycle == 1:
            expectation_deltas = [
                _expectation_delta(
                    "expectation-delta:c1:create",
                    "CREATE",
                    at=at,
                    target=None,
                    expectation=_expectation("expectation:base-sequence", hypothesis_id="hypothesis:base", revision=1, status="OPEN", created_at=at, updated_at=at, deadline="2026-08-06T04:30:00Z"),
                )
            ]
        elif cycle == 2:
            old = {row["expectation_id"]: row for row in previous_ledger["expectations"]}["expectation:base-sequence"]
            partial = {
                **old,
                "revision": 2,
                "updated_at": at,
                "status": "PARTIAL",
                "result_evidence_refs": [f"fact:c{cycle}:0"],
                "result_evidence_bindings": bindings_for(
                    [f"fact:c{cycle}:0"]
                ),
                "result_note": "first synthetic observation matches but window remains open",
            }
            expectation_deltas = [_expectation_delta("expectation-delta:c2:update", "UPDATE_RESULT", at=at, target=old["expectation_id"], expectation=partial)]
        elif cycle == 3:
            old = {row["expectation_id"]: row for row in previous_ledger["expectations"]}["expectation:base-sequence"]
            result_evidence_refs = sorted(
                set(old["result_evidence_refs"]) | {f"fact:c{cycle}:0"}
            )
            closed = {
                **old,
                "revision": 3,
                "updated_at": at,
                "status": "FULFILLED",
                "result_evidence_refs": result_evidence_refs,
                "result_evidence_bindings": {
                    **old["result_evidence_bindings"],
                    **bindings_for([f"fact:c{cycle}:0"]),
                },
                "closed_at": at,
                "result_note": "registered synthetic sequence was observed before deadline",
            }
            expectation_deltas = [_expectation_delta("expectation-delta:c3:close", "CLOSE", at=at, target=old["expectation_id"], expectation=closed)]
        else:
            expectation_deltas = [
                _expectation_delta(
                    "expectation-delta:c4:create-novel",
                    "CREATE",
                    at=at,
                    target=None,
                    expectation=_expectation("expectation:novel-liquidity-response", hypothesis_id="hypothesis:event-liquidity-vacuum-reversal", revision=1, status="OPEN", created_at=at, updated_at=at, deadline="2026-08-06T08:30:00Z"),
                )
            ]
        registry_ids = (
            {row["hypothesis_id"] for row in previous_registry["hypotheses"]}
            if previous_registry
            else {"hypothesis:base", "hypothesis:pullback", "hypothesis:residual"}
        )
        registry_ids |= {
            row["hypothesis_id"]
            for delta in hypothesis_deltas
            for row in delta["replacement_hypotheses"]
        }
        lead = "hypothesis:event-liquidity-vacuum-reversal" if cycle >= 3 else "hypothesis:base"
        runner = "hypothesis:event-liquidity-vacuum-reversal" if cycle == 2 else "hypothesis:pullback" if cycle == 1 else "hypothesis:base"
        residual = "hypothesis:residual"
        if not {lead, runner, residual}.issubset(registry_ids):
            raise ContinuousFixtureInfrastructureError("FIXTURE_OPERATIONAL_PATH_SET_INVALID")
        expectation_id = (
            "expectation:novel-liquidity-response"
            if cycle == 4
            else "expectation:base-sequence"
        )
        expectation_effect = {
            1: "CREATE",
            2: "PARTIAL",
            3: "FULFILL",
            4: "CREATE",
        }[cycle]
        mechanism_target = (
            "hypothesis:event-liquidity-vacuum-reversal"
            if cycle >= 2
            else lead
        )
        hypothesis_effect = {
            1: "SUPPORT",
            2: "CREATE_CANDIDATE",
            3: "PROMOTE",
            4: "REVISE",
        }[cycle]
        belief_events = []
        if cycle == 1:
            for index, path_id in enumerate((lead, runner, residual)):
                belief_events.append(
                    {
                        "event_id": f"belief-event:c1:{index}",
                        "operation": "ADD",
                        "path_id": path_id,
                        "evidence_id": f"belief-evidence:c1:{index}",
                        "lineage_key": f"fixture-lineage:{index}",
                        "direction": "SUPPORT",
                        "strength": 1,
                        "available_at": at,
                        "source_ref": f"fact:c1:{index}",
                        "premise_ref": f"premise:{path_id}",
                        "supersedes_evidence_id": None,
                    }
                )
        else:
            path_id = lead if cycle >= 3 else runner
            belief_events.append(
                {
                    "event_id": f"belief-event:c{cycle}:novel",
                    "operation": "ADD",
                    "path_id": path_id,
                    "evidence_id": f"belief-evidence:c{cycle}:novel",
                    "lineage_key": f"fixture-novel-lineage:c{cycle}",
                    "direction": "SUPPORT",
                    "strength": 1,
                    "available_at": at,
                    "source_ref": f"fact:c{cycle}:3",
                    "premise_ref": f"premise:{path_id}",
                    "supersedes_evidence_id": None,
                }
            )
        position_truth = build_lot_position_truth(
            symbol="SYNTHUSDT", position_truth=context["portfolio_truth"]
        )
        payload = {
            "sentiment_dimension_inputs": dimensions,
            "operational_synthesis": "conditional synthetic state with explicit unknowns and no probability",
            "hypothesis_deltas": hypothesis_deltas,
            "expectation_deltas": expectation_deltas,
            "belief_events": belief_events,
            "operational_lead_path_id": lead,
            "runner_up_path_id": runner,
            "residual_path_id": residual,
            "candidate_proposals": _candidate_rows(
                cycle_index=cycle,
                lead=lead,
                runner=runner,
                residual=residual,
                position_truth_digest=position_truth["position_truth_digest"],
            ),
            "public_inference_claims": _public_inference_claims(
                cycle_index=cycle,
                lead=lead,
                mechanism_target=mechanism_target,
                expectation_id=expectation_id,
                expectation_effect=expectation_effect,
                hypothesis_effect=hypothesis_effect,
                market_snapshot=snapshot,
            ),
            "dynamic_update_from_cycle_index": cycle - 1,
            "dynamic_update_summary": (
                "genesis has no prior accepted cycle"
                if cycle == 1
                else f"Cycle {cycle - 1} is the sole prior accepted state for this update"
            ),
            "agent_rationale": "update mechanisms and expectations before comparing the complete action set",
        }
        delivery = self._complete_delivery(
            run_id=run_id,
            cycle_index=cycle,
            input_digest=input_digest,
            expected_schema_id="synthetic_open_research_agent_payload",
            payload=payload,
            adapter_receipt_id=f"synthetic-proposal-delivery:{cycle}",
        )
        return self._persist_transport_delivery(
            kind="proposal",
            run_id=run_id,
            cycle_index=cycle,
            input_digest=input_digest,
            delivery=delivery,
        )

    def deliberate(self, *, evaluation_set: Mapping[str, Any]) -> Mapping[str, Any]:
        run_id = str(evaluation_set["run_id"])
        cycle_index = int(evaluation_set["cycle_index"])
        input_digest = str(evaluation_set["action_evaluation_digest"])
        recovered = self._load_transport_delivery(
            kind="deliberation",
            run_id=run_id,
            cycle_index=cycle_index,
            input_digest=input_digest,
        )
        if recovered is not None:
            return recovered
        feasible = [row["candidate_id"] for row in evaluation_set["candidates"] if row["feasible"]]
        selected = next(candidate_id for candidate_id in feasible if candidate_id.endswith(":hold"))
        alternatives = [candidate_id for candidate_id in feasible if candidate_id != selected]
        payload = {
            "selected_candidate_id": selected,
            "ranked_alternative_ids": alternatives,
            "why_not_selected": {candidate_id: "synthetic fixture keeps exposure unchanged while recording the alternative" for candidate_id in alternatives},
            "selection_rationale": "HOLD is selected only to exercise the state chain; it is not a market recommendation",
        }
        delivery = self._complete_delivery(
            run_id=run_id,
            cycle_index=cycle_index,
            input_digest=input_digest,
            expected_schema_id="synthetic_agent_deliberation_payload",
            payload=payload,
            adapter_receipt_id=(
                f"synthetic-deliberation-delivery:{evaluation_set['cycle_index']}"
            ),
        )
        return self._persist_transport_delivery(
            kind="deliberation",
            run_id=run_id,
            cycle_index=cycle_index,
            input_digest=input_digest,
            delivery=delivery,
        )


class SyntheticComparator:
    def compare(
        self, *, cycle_index: int, accepted_state: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        selected = str(accepted_state["selected_candidate_id"])
        return {
            "cycle_index": cycle_index,
            "lead_path_id": str(accepted_state["operational_lead_path_id"]),
            "lead_prefix_status": "SUPPORTED" if cycle_index < 4 else "UNRESOLVED",
            "selected_candidate_id": selected,
            "applied_candidate_id": selected,
            "agent_net_pnl_usdt": str(-cycle_index),
            "baseline_net_pnl_usdt": str(-cycle_index - 1),
            "available_favorable_move_usdt": "10",
            "captured_favorable_move_usdt": "5",
            "available_add_risk_usdt": "20",
            "deployed_add_risk_usdt": "0",
            "reentry_status": "NOT_APPLICABLE",
            "eligible_reentry_at": None,
            "reentered_at": None,
            "fees_usdt": "0",
            "funding_status": "UNKNOWN",
            "funding_usdt": None,
            "equity_usdt": str(100 - cycle_index),
            "peak_equity_usdt": "100",
        }
