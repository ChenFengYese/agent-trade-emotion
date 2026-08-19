"""Single-authority atomic commit store for the offline E0 runtime."""

from __future__ import annotations

import fcntl
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from .models import CommitReceipt, E0CommitPlan


ZERO_DIGEST = "0" * 64
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EventStoreError(ValueError):
    pass


def _receipt_from_mapping(value: Mapping[str, Any]) -> CommitReceipt:
    return CommitReceipt(
        commit_id=str(value["commit_id"]),
        idempotent_command_id=str(value["idempotent_command_id"]),
        input_digest=str(value["input_digest"]),
        batch_digest=str(value["batch_digest"]),
        first_event_sequence=int(value["first_event_sequence"]),
        last_event_sequence=int(value["last_event_sequence"]),
        event_chain_head_digest=str(value["event_chain_head_digest"]),
        committed_at=str(value["committed_at"]),
        aggregate_head_digests=tuple(
            (str(item[0]), str(item[1]))
            for item in value["aggregate_head_digests"]
        ),
        receipt_digest=str(value["receipt_digest"]),
    )


class FileUnitOfWork:
    """Persist each complete batch as one immutable transaction file.

    The mutable `head.json` is a recoverable accelerator only. Accepted truth is
    the longest valid chain of immutable commit files.
    """

    def __init__(self, runtime_root: Path, offline_run_id: str) -> None:
        if _SAFE_RUN_ID.fullmatch(offline_run_id) is None or offline_run_id in {
            "current",
            "latest",
        }:
            raise EventStoreError("EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED")
        self.offline_run_id = offline_run_id
        self.run_root = Path(runtime_root).resolve() / offline_run_id
        self.repo_root = self.run_root / "repository"
        self.commits_root = self.repo_root / "commits"
        self.commits_root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.repo_root / "commit.lock"
        self.lock_path.touch(exist_ok=True)

    def _read_commits(self) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        expected_sequence: int | None = None
        expected_digest: str | None = None
        for path in sorted(self.commits_root.glob("*.commit.json")):
            try:
                transaction = load_json_strict(path)
                verify_self_digest(transaction, "transaction_digest")
                receipt = transaction["receipt"]
                supplied_receipt_digest = receipt["receipt_digest"]
                unsigned_receipt = dict(receipt)
                unsigned_receipt.pop("receipt_digest", None)
                if supplied_receipt_digest != canonical_digest(unsigned_receipt):
                    break
                events = transaction["stored_events"]
                if not events:
                    break
                first_sequence = events[0]["event_sequence"]
                previous_event_digest = events[0]["previous_event_digest"]
                if expected_sequence is None:
                    if first_sequence != 0 or previous_event_digest != ZERO_DIGEST:
                        break
                elif (
                    first_sequence != expected_sequence + 1
                    or previous_event_digest != expected_digest
                ):
                    break
                chain_digest = previous_event_digest
                sequence = first_sequence
                for event in events:
                    if (
                        event["event_sequence"] != sequence
                        or event["previous_event_digest"] != chain_digest
                    ):
                        return valid
                    unsigned_event = dict(event)
                    supplied = unsigned_event.pop("event_digest")
                    if supplied != canonical_digest(unsigned_event):
                        return valid
                    chain_digest = supplied
                    sequence += 1
                if receipt["event_chain_head_digest"] != chain_digest:
                    break
                valid.append(transaction)
                expected_sequence = events[-1]["event_sequence"]
                expected_digest = chain_digest
            except (KeyError, TypeError, ValueError):
                break
        return valid

    def recover(self) -> dict[str, Any]:
        commits = self._read_commits()
        if not commits:
            return {
                "event_sequence": None,
                "event_digest": None,
                "aggregate_heads": {},
                "commits": (),
            }
        aggregate_heads: dict[str, dict[str, Any]] = {}
        for transaction in commits:
            for head in transaction["aggregate_heads"]:
                aggregate_heads[head["aggregate_id"]] = head
        last = commits[-1]
        return {
            "event_sequence": last["receipt"]["last_event_sequence"],
            "event_digest": last["receipt"]["event_chain_head_digest"],
            "aggregate_heads": aggregate_heads,
            "commits": tuple(commits),
        }

    def _find_idempotent(
        self, recovered: Mapping[str, Any], command_id: str
    ) -> dict[str, Any] | None:
        for transaction in recovered["commits"]:
            if transaction["receipt"]["idempotent_command_id"] == command_id:
                return transaction
        return None

    def commit(self, plan: E0CommitPlan) -> CommitReceipt:
        if (
            plan.offline_run_id != self.offline_run_id
            or plan.system_mode != SYSTEM_MODE
            or plan.external_execution_authority != EXTERNAL_EXECUTION_AUTHORITY
            or plan.executable
        ):
            raise EventStoreError("EXTERNAL_EXECUTION_FORBIDDEN_E0")
        if not plan.events or not plan.aggregate_updates:
            raise EventStoreError("UOW_RECOVERY_REQUIRED")
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
            plan.committed_at,
        ) is None:
            raise EventStoreError("CLOCK_TIME_INVALID")
        if set(plan.conditional_future_action_refs) & set(plan.atomic_effect_refs):
            raise EventStoreError("RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED")
        cause_event_ids = {event.event_id for event in plan.events}
        if any(
            update.cause_event_id not in cause_event_ids
            for update in plan.aggregate_updates
        ):
            raise EventStoreError("UOW_RECOVERY_REQUIRED")
        plan_mapping = asdict(plan)
        input_digest = canonical_digest(plan_mapping)
        with self.lock_path.open("r+b") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            recovered = self.recover()
            duplicate = self._find_idempotent(
                recovered, plan.idempotent_command_id
            )
            if duplicate is not None:
                receipt = duplicate["receipt"]
                if receipt["input_digest"] != input_digest:
                    raise EventStoreError("UOW_PARTIAL_DUPLICATE")
                return _receipt_from_mapping(receipt)
            if (
                recovered["event_sequence"] != plan.expected_previous_event_sequence
                or recovered["event_digest"] != plan.expected_previous_event_digest
            ):
                raise EventStoreError("UOW_HEAD_STALE")
            preconditions = {item.aggregate_id: item for item in plan.aggregate_preconditions}
            updates = {item.aggregate_id: item for item in plan.aggregate_updates}
            if len(preconditions) != len(plan.aggregate_preconditions) or len(
                updates
            ) != len(plan.aggregate_updates):
                raise EventStoreError("UOW_PARTIAL_DUPLICATE")
            if set(preconditions) != set(updates):
                raise EventStoreError("UOW_RECOVERY_REQUIRED")
            for aggregate_id, precondition in preconditions.items():
                accepted = recovered["aggregate_heads"].get(aggregate_id)
                accepted_revision = 0 if accepted is None else accepted["aggregate_revision"]
                accepted_digest = None if accepted is None else accepted["state_digest"]
                if (
                    precondition.expected_revision != accepted_revision
                    or precondition.expected_state_digest != accepted_digest
                ):
                    raise EventStoreError("UOW_HEAD_STALE")
                if updates[aggregate_id].next_revision != accepted_revision + 1:
                    raise EventStoreError("UOW_HEAD_STALE")
            first_sequence = (
                0
                if recovered["event_sequence"] is None
                else recovered["event_sequence"] + 1
            )
            prior_digest = recovered["event_digest"] or ZERO_DIGEST
            stored_events: list[dict[str, Any]] = []
            sequence_by_event_id: dict[str, int] = {}
            digest_by_event_id: dict[str, str] = {}
            for offset, draft in enumerate(plan.events):
                sequence = first_sequence + offset
                unsigned_event = {
                    "offline_run_id": self.offline_run_id,
                    "event_sequence": sequence,
                    "event_id": draft.event_id,
                    "event_type": draft.event_type,
                    "payload_schema_id": draft.payload_schema_id,
                    "payload_ref": draft.payload_ref,
                    "payload_digest": draft.payload_digest,
                    "aggregate_id": draft.aggregate_id,
                    "previous_event_digest": prior_digest,
                    "system_mode": SYSTEM_MODE,
                    "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                    "executable": False,
                }
                event = {**unsigned_event, "event_digest": canonical_digest(unsigned_event)}
                stored_events.append(event)
                prior_digest = event["event_digest"]
                sequence_by_event_id[draft.event_id] = sequence
                digest_by_event_id[draft.event_id] = prior_digest
            committed_at = plan.committed_at
            aggregate_heads: list[dict[str, Any]] = []
            for update in sorted(plan.aggregate_updates, key=lambda item: item.aggregate_id):
                prior_head = recovered["aggregate_heads"].get(update.aggregate_id)
                unsigned_head = {
                    "aggregate_id": update.aggregate_id,
                    "aggregate_type": update.aggregate_type,
                    "aggregate_revision": update.next_revision,
                    "state_ref": update.state_ref,
                    "state_digest": update.state_digest,
                    "last_event_id": update.cause_event_id,
                    "last_event_sequence": sequence_by_event_id[update.cause_event_id],
                    "last_event_digest": digest_by_event_id[update.cause_event_id],
                    "previous_head_digest": (
                        None if prior_head is None else prior_head["head_digest"]
                    ),
                    "committed_at": committed_at,
                }
                aggregate_heads.append(
                    {**unsigned_head, "head_digest": canonical_digest(unsigned_head)}
                )
            unsigned_batch = {
                "commit_id": plan.commit_id,
                "offline_run_id": self.offline_run_id,
                "decision_session_id": plan.decision_session_id,
                "input_digest": input_digest,
                "accepted_artifact_digests": list(plan.accepted_artifact_digests),
                "receding_horizon_plan_ref": plan.receding_horizon_plan_ref,
                "authorized_first_step_action_ref": plan.authorized_first_step_action_ref,
                "atomic_effect_refs": list(plan.atomic_effect_refs),
                "counterfactual_policy_ref": plan.counterfactual_policy_ref,
                "portfolio_replay_result_ref": plan.portfolio_replay_result_ref,
                "first_event_sequence": first_sequence,
                "last_event_sequence": stored_events[-1]["event_sequence"],
                "event_chain_head_digest": stored_events[-1]["event_digest"],
                "aggregate_head_digests": [
                    [head["aggregate_id"], head["head_digest"]]
                    for head in aggregate_heads
                ],
            }
            batch_digest = canonical_digest(unsigned_batch)
            unsigned_receipt = {
                "commit_id": plan.commit_id,
                "idempotent_command_id": plan.idempotent_command_id,
                "input_digest": input_digest,
                "batch_digest": batch_digest,
                "first_event_sequence": first_sequence,
                "last_event_sequence": stored_events[-1]["event_sequence"],
                "event_chain_head_digest": stored_events[-1]["event_digest"],
                "committed_at": committed_at,
                "aggregate_head_digests": unsigned_batch["aggregate_head_digests"],
            }
            receipt = {
                **unsigned_receipt,
                "receipt_digest": canonical_digest(unsigned_receipt),
            }
            transaction = self_digest(
                {
                    "transaction_schema": "theory_agent_v2.atomic_commit.v1",
                    "batch": {**unsigned_batch, "batch_digest": batch_digest},
                    "stored_events": stored_events,
                    "aggregate_heads": aggregate_heads,
                    "receipt": receipt,
                },
                "transaction_digest",
            )
            filename = (
                f"{first_sequence:020d}-{stored_events[-1]['event_sequence']:020d}-"
                f"{plan.commit_id}.commit.json"
            )
            target = self.commits_root / filename
            if target.exists():
                raise EventStoreError("UOW_PARTIAL_DUPLICATE")
            payload = canonical_bytes(transaction) + b"\n"
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".uow-", suffix=".tmp", dir=self.commits_root
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, target)
                directory_fd = os.open(self.commits_root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temporary.unlink(missing_ok=True)
            return _receipt_from_mapping(receipt)

    def read_after(self, chain_cursor: int | None) -> tuple[dict[str, Any], ...]:
        events = [
            event
            for transaction in self.recover()["commits"]
            for event in transaction["stored_events"]
        ]
        if chain_cursor is None:
            return tuple(events)
        return tuple(event for event in events if event["event_sequence"] > chain_cursor)

    def load_commit(self, commit_id: str) -> CommitReceipt:
        for transaction in self.recover()["commits"]:
            if transaction["receipt"]["commit_id"] == commit_id:
                return _receipt_from_mapping(transaction["receipt"])
        raise EventStoreError("COMMIT_RECEIPT_MISSING")
