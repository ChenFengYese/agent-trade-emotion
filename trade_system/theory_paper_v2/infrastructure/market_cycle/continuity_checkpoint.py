"""Create-only continuity checkpoints over existing V3.3.2 fact owners.

This adapter is not a runner or scheduler.  It samples the run, controller,
cycle, paper and Agent-authored next-check owners at a trusted clock instant
and publishes an immutable hash chain.  A check window is classified only
when a later cycle contains an actually delivered Agent decision.  Recovery
never waits for, wakes, approves, spawns, or advances the trading Agent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
from ...domain.market_cycle.continuity import (
    ABSOLUTE_SLOT_GAP,
    FINALIZATION_AWAITING_RUN_CLOSE,
    ContinuityCheckpointV1,
    ContinuityContractError,
    ContinuityRecoveryV1,
    RECOVERY_FORBIDDEN_DUPLICATES,
    RecoveryObservationV1,
    RecoveryProbeV1,
    absolute_slot,
    scheduled_at,
)
from ...domain.market_cycle.experiment import ExperimentPolicyV1
from ...application.market_cycle.attention import AttentionService
from ...v32_durable_json import (
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from .attention_repository import FileAttentionRepository
from .paper_ledger import FilePaperLedger
from .runtime import run_lifecycle_lock


OWNER_HEAD_DIVERGENCE = "OWNER_HEAD_DIVERGENCE"
_MAX_RECORDS = 100_000
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_PROBE_BYTES = 4 * 1024 * 1024
_SAFE_PROBE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}\Z")


class ContinuityCheckpointError(RuntimeError):
    """The checkpoint chain or an observed fact-owner head is unsafe."""


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ContinuityCheckpointError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuityCheckpointError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuityCheckpointError(code)
    return parsed


def _read_record(path: Path) -> ContinuityCheckpointV1:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ContinuityCheckpointError("CONTINUITY_RECORD_MISSING") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_RECORD_BYTES
    ):
        raise ContinuityCheckpointError("CONTINUITY_RECORD_UNSAFE")
    raw = path.read_bytes()
    if len(raw) != metadata.st_size:
        raise ContinuityCheckpointError("CONTINUITY_RECORD_SHORT_READ")
    try:
        value = loads_json_strict(raw)
        if not isinstance(value, Mapping) or canonical_bytes(value) + b"\n" != raw:
            raise ContinuityCheckpointError("CONTINUITY_RECORD_NONCANONICAL")
        return ContinuityCheckpointV1.from_dict(value)
    except (CanonicalContractError, ContinuityContractError) as exc:
        raise ContinuityCheckpointError("CONTINUITY_RECORD_INVALID") from exc


def _probe_id(value: object) -> str:
    if type(value) is not str or _SAFE_PROBE_ID.fullmatch(value) is None:
        raise ContinuityCheckpointError("CONTINUITY_RECOVERY_PROBE_ID_INVALID")
    return value


def _read_probe(path: Path) -> RecoveryProbeV1:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ContinuityCheckpointError("CONTINUITY_RECOVERY_PROBE_MISSING") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_PROBE_BYTES
    ):
        raise ContinuityCheckpointError("CONTINUITY_RECOVERY_PROBE_UNSAFE")
    raw = path.read_bytes()
    try:
        value = loads_json_strict(raw)
        if canonical_bytes(value) + b"\n" != raw:
            raise ContinuityCheckpointError(
                "CONTINUITY_RECOVERY_PROBE_NONCANONICAL"
            )
        return RecoveryProbeV1.from_dict(value)
    except (CanonicalContractError, ContinuityContractError) as exc:
        raise ContinuityCheckpointError("CONTINUITY_RECOVERY_PROBE_INVALID") from exc


def _read_observation(path: Path) -> RecoveryObservationV1:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ContinuityCheckpointError(
            "CONTINUITY_RECOVERY_OBSERVATION_MISSING"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_PROBE_BYTES
    ):
        raise ContinuityCheckpointError(
            "CONTINUITY_RECOVERY_OBSERVATION_UNSAFE"
        )
    raw = path.read_bytes()
    try:
        value = loads_json_strict(raw)
        if canonical_bytes(value) + b"\n" != raw:
            raise ContinuityCheckpointError(
                "CONTINUITY_RECOVERY_OBSERVATION_NONCANONICAL"
            )
        return RecoveryObservationV1.from_dict(value)
    except (CanonicalContractError, ContinuityContractError) as exc:
        raise ContinuityCheckpointError(
            "CONTINUITY_RECOVERY_OBSERVATION_INVALID"
        ) from exc


class FileContinuityCheckpointStore:
    """Read fact-owner heads and maintain one immutable checkpoint chain."""

    def __init__(self, runtime: object, *, clock: object) -> None:
        policy = getattr(runtime, "experiment_policy", None)
        manifest = getattr(runtime, "run_manifest", None)
        root = getattr(runtime, "runtime_root", None)
        if (
            not isinstance(policy, ExperimentPolicyV1)
            or manifest is None
            or manifest.run_id != policy.run_id
            or manifest.experiment_identity != policy.policy_sha256
            or not isinstance(root, Path)
            or not callable(clock)
        ):
            raise ContinuityCheckpointError("CONTINUITY_CONFIGURATION_INVALID")
        if policy.duration_seconds % policy.base_sampling_seconds != 0:
            raise ContinuityCheckpointError(
                "CONTINUITY_DURATION_NOT_ALIGNED_TO_BASE_SLOT"
            )
        self._runtime = runtime
        self._policy = policy
        self._clock = clock
        self._root = root / "controller" / "continuity"
        self._records_root = self._root / "records"
        self._probes_root = self._root / "recovery-probes"
        self._lock_path = self._root / "checkpoint.lock"

    def _mutation_guard(self):  # noqa: ANN201 - context manager proxy
        guard = getattr(self._runtime, "mutation_guard", None)
        return guard() if callable(guard) else run_lifecycle_lock(
            self._runtime.runtime_root
        )

    def _now(self) -> str:
        value = self._clock()
        _moment(value, code="CONTINUITY_CLOCK_INVALID")
        return value

    def _classify_issue(self, issue_code: str) -> str:
        if issue_code in self._policy.restart_if:
            return "RESTART_REQUIRED"
        if issue_code in self._policy.continue_if:
            return "CONTINUE"
        raise ContinuityCheckpointError(
            f"CONTINUITY_ISSUE_NOT_CLASSIFIED:{issue_code}"
        )

    def _record_path(self, sequence: int) -> Path:
        return self._records_root / f"{sequence:08d}.json"

    def _probe_root(self, probe_id: str) -> Path:
        return self._probes_root / _probe_id(probe_id)

    def _require_recovery_policy(self) -> None:
        if (
            self._policy.phase != "CAPABILITY_PILOT"
            or self._policy.capability_ids != ("RECOVERY_REPLAY",)
        ):
            raise ContinuityCheckpointError(
                "CONTINUITY_RECOVERY_SINGLE_CAPABILITY_POLICY_REQUIRED"
            )

    def _replay_locked(self) -> tuple[ContinuityCheckpointV1, ...]:
        try:
            metadata = self._records_root.lstat()
        except FileNotFoundError:
            return ()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ContinuityCheckpointError("CONTINUITY_RECORD_DIRECTORY_UNSAFE")
        paths = sorted(self._records_root.iterdir())
        if len(paths) > _MAX_RECORDS:
            raise ContinuityCheckpointError("CONTINUITY_RECORD_CAPACITY_EXCEEDED")
        records: list[ContinuityCheckpointV1] = []
        previous_sha: str | None = None
        previous_slot = 0
        previous_observed: datetime | None = None
        seen_attention_requests: set[str] = set()
        for sequence, path in enumerate(paths, start=1):
            if (
                path.name != f"{sequence:08d}.json"
                or path.is_symlink()
                or not path.is_file()
            ):
                raise ContinuityCheckpointError("CONTINUITY_RECORD_SEQUENCE_GAP")
            record = _read_record(path)
            if (
                record.sequence != sequence
                or record.run_id != self._policy.run_id
                or record.policy_sha256 != self._policy.policy_sha256
                or record.previous_record_sha256 != previous_sha
            ):
                raise ContinuityCheckpointError("CONTINUITY_RECORD_CHAIN_INVALID")
            if record.slot_kind in {"BASE", "FINAL"} and (
                record.slot_scheduled_at
                != scheduled_at(
                    self._policy.starts_at,
                    self._policy.base_sampling_seconds,
                    record.absolute_slot,
                )
            ):
                raise ContinuityCheckpointError("CONTINUITY_RECORD_CHAIN_INVALID")
            if record.slot_kind == "AGENT_ATTENTION":
                assert record.source_event_id is not None
                if record.source_event_id in seen_attention_requests:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_ATTENTION_REQUEST_REUSED"
                    )
                seen_attention_requests.add(record.source_event_id)
            observed = _moment(
                record.observed_at, code="CONTINUITY_RECORD_TIME_INVALID"
            )
            if sequence == 1:
                if record.record_kind != "OPEN" or record.absolute_slot != 0:
                    raise ContinuityCheckpointError("CONTINUITY_OPEN_RECORD_INVALID")
            elif (
                record.record_kind == "OPEN"
                or record.absolute_slot < previous_slot
                or (previous_observed is not None and observed < previous_observed)
            ):
                raise ContinuityCheckpointError("CONTINUITY_RECORD_ORDER_INVALID")
            if record.issue_code is not None:
                expected = self._classify_issue(record.issue_code)
                if record.disposition != expected:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_ISSUE_DISPOSITION_INVALID"
                    )
            if records[-1].record_kind == "FINAL" if records else False:
                raise ContinuityCheckpointError("CONTINUITY_RECORD_AFTER_FINAL")
            if records and records[-1].disposition == "RESTART_REQUIRED":
                raise ContinuityCheckpointError("CONTINUITY_RECORD_AFTER_RESTART")
            records.append(record)
            previous_sha = record.record_sha256
            previous_slot = record.absolute_slot
            previous_observed = observed
        return tuple(records)

    def _cycle_heads(self) -> list[dict[str, Any]]:
        repository = getattr(self._runtime, "repository", None)
        service = getattr(self._runtime, "service", None)
        root = getattr(repository, "root", None)
        if not isinstance(root, Path) or service is None:
            raise ContinuityCheckpointError("CONTINUITY_CYCLE_OWNER_UNAVAILABLE")
        try:
            metadata = root.lstat()
        except FileNotFoundError:
            return []
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ContinuityCheckpointError("CONTINUITY_CYCLE_OWNER_UNSAFE")
        list_cycle_ids = getattr(repository, "list_cycle_ids", None)
        if callable(list_cycle_ids):
            try:
                cycle_ids = tuple(list_cycle_ids())
            except Exception as exc:
                raise ContinuityCheckpointError(
                    "CONTINUITY_CYCLE_OWNER_UNSAFE"
                ) from exc
        else:
            cycle_ids = tuple(
                path.name
                for path in sorted(root.iterdir(), key=lambda item: item.name)
                if path.name != ".locks"
            )
        if len(cycle_ids) != len(set(cycle_ids)):
            raise ContinuityCheckpointError("CONTINUITY_CYCLE_OWNER_UNSAFE")
        result: list[dict[str, Any]] = []
        for cycle_id in cycle_ids:
            path = root / cycle_id
            if path.is_symlink() or not path.is_dir():
                raise ContinuityCheckpointError("CONTINUITY_CYCLE_ENTRY_UNSAFE")
            try:
                service.verify_cycle_read(cycle_id)
                state = repository.load_state(cycle_id)
                request = repository.load_request(cycle_id)
            except Exception as exc:
                raise ContinuityCheckpointError(
                    f"CONTINUITY_CYCLE_HEAD_INVALID:{cycle_id}"
                ) from exc
            agent_decision_delivered_at: str | None = None
            if any(
                reference.artifact_type == "HypothesisRecord"
                for reference in state.artifact_refs
            ):
                try:
                    hypothesis = repository.load_artifact(
                        cycle_id, "HypothesisRecord"
                    )
                except Exception as exc:
                    raise ContinuityCheckpointError(
                        f"CONTINUITY_CYCLE_HEAD_INVALID:{cycle_id}"
                    ) from exc
                delivered_at = hypothesis.get("agent_delivered_at")
                _moment(
                    delivered_at,
                    code="CONTINUITY_CYCLE_AGENT_DELIVERY_TIME_INVALID",
                )
                agent_decision_delivered_at = delivered_at
            result.append(
                {
                    "cycle_id": cycle_id,
                    "requested_at": request.requested_at,
                    "venue_id": request.venue_id,
                    "instrument_id": request.instrument_id,
                    "stage": state.stage,
                    "revision": state.revision,
                    "state_sha256": canonical_digest(state.to_dict()),
                    "artifact_refs": [
                        reference.to_dict() for reference in state.artifact_refs
                    ],
                    "agent_decision_delivered_at": agent_decision_delivered_at,
                }
            )
        return result

    def _owner_heads(self) -> dict[str, Any]:
        manifest = self._runtime.run_manifest
        try:
            controller = dict(self._runtime.service.controller_status())
        except Exception as exc:
            raise ContinuityCheckpointError(
                "CONTINUITY_CONTROLLER_HEAD_UNAVAILABLE"
            ) from exc
        revision = controller.get("revision")
        if type(revision) is not int or revision < 0:
            raise ContinuityCheckpointError("CONTINUITY_CONTROLLER_HEAD_INVALID")
        dispatch_mapping = controller.get("worker_dispatches")
        if not isinstance(dispatch_mapping, Mapping):
            raise ContinuityCheckpointError("CONTINUITY_CONTROLLER_HEAD_INVALID")
        worker_dispatches = []
        for dispatch_key, record in sorted(dispatch_mapping.items()):
            if not isinstance(dispatch_key, str) or not isinstance(record, Mapping):
                raise ContinuityCheckpointError(
                    "CONTINUITY_CONTROLLER_DISPATCH_HEAD_INVALID"
                )
            worker_dispatches.append(
                {
                    "dispatch_key": dispatch_key,
                    "cycle_id": record.get("cycle_id"),
                    "worker_id": record.get("worker_id"),
                    "dispatch_id": record.get("dispatch_id"),
                    "status": record.get("status"),
                    "task_sha256": record.get("task_sha256"),
                    "request_sha256": record.get("request_sha256"),
                    "spawn_requested_at": record.get("spawn_requested_at"),
                    "spawn_execution_ref": record.get("spawn_execution_ref"),
                    "spawn_acknowledged_at": record.get(
                        "spawn_acknowledged_at"
                    ),
                    "output_sha256": record.get("output_sha256"),
                }
            )

        account_policy = self._policy.paper_account
        if account_policy is None:
            paper = {
                "status": "NOT_INCLUDED",
                "account_id": None,
                "revision": 0,
                "record_sha256": None,
                "events": [],
            }
            attention = {
                "status": "NOT_INCLUDED",
                "logical_agent_id": None,
                "revision": 0,
                "event_sha256": None,
                "events": [],
            }
        else:
            account_id = str(account_policy["account_id"])
            records = FilePaperLedger(
                self._runtime.runtime_root / "paper"
            ).load_records(account_id)
            paper = {
                "status": "OPENED" if records else "NOT_OPENED",
                "account_id": account_id,
                "revision": len(records),
                "record_sha256": records[-1].record_sha256 if records else None,
                "events": [
                    {
                        "event_id": record.event_id,
                        "event_type": record.event_type,
                        "record_sha256": record.record_sha256,
                    }
                    for record in records
                ],
            }
            logical_agent_id = str(account_policy["logical_agent_id"])
            attention_repository = FileAttentionRepository(
                self._runtime.runtime_root / "attention"
            )
            attention_head = attention_repository.load(logical_agent_id)
            attention_events = attention_repository.replay(logical_agent_id)
            attention = {
                "status": "PRESENT" if attention_head.revision else "EMPTY",
                "logical_agent_id": logical_agent_id,
                "revision": attention_head.revision,
                "event_sha256": attention_head.event_sha256,
                "events": [
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "event_sha256": event.event_sha256,
                    }
                    for event in attention_events
                ],
            }
        return {
            "run": {
                "run_id": manifest.run_id,
                "identity_sha256": manifest.identity_sha256,
                "manifest_status": manifest.status,
            },
            "controller": {
                "revision": revision,
                "state_sha256": canonical_digest(controller),
                "worker_dispatches": worker_dispatches,
            },
            "cycles": self._cycle_heads(),
            "paper": paper,
            "attention": attention,
        }

    def _followup_decision(
        self, request: object, heads: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        """Return the first terminal Agent decision started for this window.

        A requested or input-only cycle is not evidence that the trading Agent
        looked at the market.  The immutable cycle request binds the attempt to
        the AttentionRequest window; HypothesisRecord delivery proves that the
        selected attempt later reached an Agent decision.
        """

        earliest = _moment(
            getattr(request, "earliest"),
            code="CONTINUITY_ATTENTION_SCHEDULE_INVALID",
        )
        candidates: list[tuple[datetime, datetime, Mapping[str, Any]]] = []
        for cycle in heads.get("cycles", ()):  # type: ignore[union-attr]
            if not isinstance(cycle, Mapping):
                raise ContinuityCheckpointError("CONTINUITY_CYCLE_HEAD_INVALID")
            delivered_text = cycle.get("agent_decision_delivered_at")
            if delivered_text is None:
                continue
            requested = _moment(
                cycle.get("requested_at"),
                code="CONTINUITY_CYCLE_REQUEST_TIME_INVALID",
            )
            delivered = _moment(
                delivered_text,
                code="CONTINUITY_CYCLE_AGENT_DELIVERY_TIME_INVALID",
            )
            if delivered < requested:
                raise ContinuityCheckpointError(
                    "CONTINUITY_CYCLE_AGENT_DELIVERY_BEFORE_REQUEST"
                )
            # The run policy already fixes venue and instrument.  Recheck the
            # exact instrument here so an unrelated cycle cannot satisfy the
            # Agent's checkpoint.  ``venue_id`` is retained in owner heads for
            # audit, while symbol identity is exact at the instrument level.
            # A cycle already in progress before this request is not its
            # follow-up, even if its Agent decision is delivered in the window.
            if (
                cycle.get("instrument_id") != getattr(request, "symbol")
                or cycle.get("venue_id") != self._policy.venue_id
                or requested < earliest
            ):
                continue
            candidates.append((requested, delivered, cycle))
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (item[0], item[1], str(item[2].get("cycle_id")))
        )
        return candidates[0][2]

    @staticmethod
    def _compare_owner_heads(
        previous: Mapping[str, Any], current: Mapping[str, Any]
    ) -> str:
        # Domain contracts recursively freeze arrays as tuples.  Compare the
        # canonical JSON projection, not Python container implementation types.
        previous = loads_json_strict(canonical_bytes(previous))
        current = loads_json_strict(canonical_bytes(current))
        progressed = False
        if previous.get("run") != current.get("run"):
            raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)

        def monotonic(owner: str, digest_field: str) -> None:
            nonlocal progressed
            before = previous.get(owner)
            after = current.get(owner)
            if not isinstance(before, Mapping) or not isinstance(after, Mapping):
                raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)
            identity_fields = set(before) - {
                "revision",
                digest_field,
                "status",
                "events",
                "worker_dispatches",
            }
            if any(before.get(field) != after.get(field) for field in identity_fields):
                raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)
            before_revision = before.get("revision")
            after_revision = after.get("revision")
            if (
                type(before_revision) is not int
                or type(after_revision) is not int
                or after_revision < before_revision
                or (after_revision == before_revision and before != after)
            ):
                raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)
            progressed = progressed or after_revision > before_revision

        monotonic("controller", "state_sha256")
        monotonic("paper", "record_sha256")
        monotonic("attention", "event_sha256")

        before_cycles = {
            item["cycle_id"]: item
            for item in previous.get("cycles", [])
            if isinstance(item, Mapping) and isinstance(item.get("cycle_id"), str)
        }
        after_cycles = {
            item["cycle_id"]: item
            for item in current.get("cycles", [])
            if isinstance(item, Mapping) and isinstance(item.get("cycle_id"), str)
        }
        if (
            len(before_cycles) != len(previous.get("cycles", []))
            or len(after_cycles) != len(current.get("cycles", []))
            or not set(before_cycles) <= set(after_cycles)
        ):
            raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)
        for cycle_id, before in before_cycles.items():
            after = after_cycles[cycle_id]
            before_revision = before.get("revision")
            after_revision = after.get("revision")
            if (
                type(before_revision) is not int
                or type(after_revision) is not int
                or after_revision < before_revision
                or (after_revision == before_revision and before != after)
            ):
                raise ContinuityCheckpointError(OWNER_HEAD_DIVERGENCE)
            progressed = progressed or after_revision > before_revision
        progressed = progressed or len(after_cycles) > len(before_cycles)
        return "MONOTONIC_PROGRESS" if progressed else "UNCHANGED"

    def _publish(self, record: ContinuityCheckpointV1) -> ContinuityCheckpointV1:
        ensure_directory_tree(self._records_root)
        try:
            write_once_json(self._record_path(record.sequence), record.to_dict())
        except (OSError, CanonicalContractError) as exc:
            raise ContinuityCheckpointError(
                "CONTINUITY_RECORD_WRITE_FAILED"
            ) from exc
        return _read_record(self._record_path(record.sequence))

    @staticmethod
    def _last_base_slot(records: tuple[ContinuityCheckpointV1, ...]) -> int:
        """Agent checkpoint evidence is supplementary, never a BASE heartbeat."""

        return max(
            record.absolute_slot
            for record in records
            if record.slot_kind in {"BASE", "FINAL"}
        )

    @staticmethod
    def _validate_probe_injection(
        injection_point: str, heads: Mapping[str, Any]
    ) -> None:
        cycles = heads.get("cycles")
        controller = heads.get("controller")
        paper = heads.get("paper")
        attention = heads.get("attention")
        dispatches = (
            controller.get("worker_dispatches")
            if isinstance(controller, Mapping)
            else None
        )
        if injection_point == "INPUT_SEALED_RESTART":
            matches = [
                item
                for item in cycles or []
                if isinstance(item, Mapping) and item.get("stage") == "INPUT_SEALED"
            ]
        elif injection_point == "WORKER_PREPARED_RESTART":
            matches = [
                item
                for item in dispatches or []
                if isinstance(item, Mapping) and item.get("status") == "PREPARED"
            ]
        elif injection_point == "PAPER_INTENT_RECORDED_RESTART":
            matches = [
                item
                for item in (paper.get("events") if isinstance(paper, Mapping) else [])
                if isinstance(item, Mapping)
                and item.get("event_type") == "INTENT_RECORDED"
            ]
        elif injection_point == "ATTENTION_REQUEST_DURABLE_RESTART":
            matches = [
                item
                for item in (
                    attention.get("events")
                    if isinstance(attention, Mapping)
                    else []
                )
                if isinstance(item, Mapping)
                and item.get("event_type") == "ATTENTION_REQUEST_SUBMITTED"
            ]
        elif injection_point == "WORKER_SPAWN_REQUESTED_BEFORE_ACK_RESTART":
            matches = [
                item
                for item in dispatches or []
                if isinstance(item, Mapping)
                and item.get("status") == "SPAWN_REQUESTED"
                and item.get("spawn_execution_ref") is None
                and item.get("spawn_acknowledged_at") is None
            ]
        else:
            raise ContinuityCheckpointError(
                "CONTINUITY_RECOVERY_INJECTION_POINT_INVALID"
            )
        if len(matches) != 1:
            raise ContinuityCheckpointError(
                "CONTINUITY_RECOVERY_INJECTION_POINT_NOT_OBSERVED"
            )

    def preregister_recovery_probe(
        self, *, probe_id: str, injection_point: str
    ) -> RecoveryProbeV1:
        """Freeze one exact local recovery boundary before process restart."""

        self._require_recovery_policy()
        root = self._probe_root(probe_id)
        path = root / "probe.json"
        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            try:
                path.lstat()
            except FileNotFoundError:
                pass
            else:
                probe = _read_probe(path)
                if (
                    probe.injection_point != injection_point
                    or probe.run_id != self._policy.run_id
                    or probe.policy_sha256 != self._policy.policy_sha256
                    or probe.run_identity_sha256
                    != self._runtime.run_manifest.identity_sha256
                ):
                    raise ContinuityCheckpointError(
                        "CONTINUITY_RECOVERY_PROBE_CONFLICT"
                    )
                return probe
            heads = self._owner_heads()
            self._validate_probe_injection(injection_point, heads)
            probe = RecoveryProbeV1(
                probe_id=probe_id,
                run_id=self._policy.run_id,
                policy_sha256=self._policy.policy_sha256,
                run_identity_sha256=self._runtime.run_manifest.identity_sha256,
                injection_point=injection_point,
                expected_owner_heads=heads,
                forbidden_duplicates=RECOVERY_FORBIDDEN_DUPLICATES[
                    injection_point
                ],
                created_at=self._now(),
                created_by="TRUSTED_CONTINUITY_CLOCK",
            )
            ensure_directory_tree(root)
            try:
                write_once_json(path, probe.to_dict())
            except (OSError, CanonicalContractError) as exc:
                raise ContinuityCheckpointError(
                    "CONTINUITY_RECOVERY_PROBE_WRITE_FAILED"
                ) from exc
            return _read_probe(path)

    def observe_recovery_probe(self, probe_id: str) -> RecoveryObservationV1:
        """Replay owners after restart without retrying or advancing any action."""

        self._require_recovery_policy()
        root = self._probe_root(probe_id)
        probe_path = root / "probe.json"
        observation_path = root / "observation.json"
        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            probe = _read_probe(probe_path)
            if (
                probe.run_id != self._policy.run_id
                or probe.policy_sha256 != self._policy.policy_sha256
                or probe.run_identity_sha256
                != self._runtime.run_manifest.identity_sha256
            ):
                raise ContinuityCheckpointError(
                    "CONTINUITY_RECOVERY_PROBE_IDENTITY_MISMATCH"
                )
            try:
                observation_path.lstat()
            except FileNotFoundError:
                pass
            else:
                observation = _read_observation(observation_path)
                if observation.probe_sha256 != probe.probe_sha256:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_RECOVERY_OBSERVATION_PROBE_MISMATCH"
                    )
                return observation

            observed_heads = self._owner_heads()
            if (
                probe.injection_point
                == "WORKER_SPAWN_REQUESTED_BEFORE_ACK_RESTART"
            ):
                replay_status = "UNRESOLVED"
                duplicate_status = "UNRESOLVED"
                action = "RESTART_REQUIRED"
                reason = "SPAWN_REQUESTED_ACK_UNRESOLVED_NO_AUTORETRY"
            elif canonical_digest(observed_heads) == canonical_digest(
                probe.expected_owner_heads
            ):
                replay_status = "IDENTICAL"
                duplicate_status = "NONE_OBSERVED"
                action = "CONTINUE"
                reason = "SAFE_LOCAL_REPLAY_IDENTICAL"
            else:
                replay_status = "OWNER_HEAD_DRIFT"
                duplicate_status = "DUPLICATE_OR_DRIFT"
                action = "RESTART_REQUIRED"
                reason = "RECOVERY_OWNER_HEAD_DRIFT"
            observation = RecoveryObservationV1(
                probe_id=probe.probe_id,
                probe_sha256=probe.probe_sha256,
                run_id=probe.run_id,
                policy_sha256=probe.policy_sha256,
                observed_at=self._now(),
                observed_owner_heads=observed_heads,
                replay_status=replay_status,
                duplicate_status=duplicate_status,
                action=action,
                reason_code=reason,
            )
            try:
                write_once_json(observation_path, observation.to_dict())
            except (OSError, CanonicalContractError) as exc:
                raise ContinuityCheckpointError(
                    "CONTINUITY_RECOVERY_OBSERVATION_WRITE_FAILED"
                ) from exc
            return _read_observation(observation_path)

    def open(self) -> ContinuityCheckpointV1:
        """Open the chain in absolute slot zero; repeated calls are idempotent."""

        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if records:
                return records[0]
            observed_at = self._now()
            slot = absolute_slot(
                self._policy.starts_at,
                self._policy.base_sampling_seconds,
                observed_at,
            )
            if slot != 0:
                raise ContinuityCheckpointError(
                    "CONTINUITY_INITIAL_ABSOLUTE_SLOT_MISSED"
                )
            return self._publish(
                ContinuityCheckpointV1(
                    run_id=self._policy.run_id,
                    policy_sha256=self._policy.policy_sha256,
                    sequence=1,
                    record_kind="OPEN",
                    previous_record_sha256=None,
                    absolute_slot=slot,
                    slot_kind="BASE",
                    source_event_id=None,
                    slot_scheduled_at=scheduled_at(
                        self._policy.starts_at,
                        self._policy.base_sampling_seconds,
                        slot,
                    ),
                    latest_useful_at=None,
                    attempt_status="NOT_ATTEMPTED",
                    observed_at=observed_at,
                    issue_code=None,
                    disposition="OPENED",
                    owner_heads=self._owner_heads(),
                    finalization_status=None,
                )
            )

    def record(self, *, issue_code: str | None = None) -> ContinuityCheckpointV1:
        """Record one heartbeat/change observation without advancing the system."""

        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if not records:
                raise ContinuityCheckpointError("CONTINUITY_NOT_OPEN")
            last = records[-1]
            if last.record_kind == "FINAL" or last.disposition == "RESTART_REQUIRED":
                raise ContinuityCheckpointError("CONTINUITY_ALREADY_TERMINAL")
            observed_at = self._now()
            slot = absolute_slot(
                self._policy.starts_at,
                self._policy.base_sampling_seconds,
                observed_at,
            )
            last_base_slot = self._last_base_slot(records)
            if slot < last_base_slot:
                raise ContinuityCheckpointError("CONTINUITY_CLOCK_SLOT_REGRESSION")
            if slot > last_base_slot + 1:
                if issue_code is not None and issue_code != ABSOLUTE_SLOT_GAP:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_MULTIPLE_ISSUES_UNSUPPORTED"
                    )
                issue_code = ABSOLUTE_SLOT_GAP
            disposition = (
                "CONTINUE" if issue_code is None else self._classify_issue(issue_code)
            )
            heads = self._owner_heads()
            try:
                self._compare_owner_heads(last.owner_heads, heads)
            except ContinuityCheckpointError as exc:
                if str(exc) != OWNER_HEAD_DIVERGENCE:
                    raise
                if issue_code is not None and issue_code != OWNER_HEAD_DIVERGENCE:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_MULTIPLE_ISSUES_UNSUPPORTED"
                    )
                issue_code = OWNER_HEAD_DIVERGENCE
                disposition = self._classify_issue(issue_code)
            return self._publish(
                ContinuityCheckpointV1(
                    run_id=self._policy.run_id,
                    policy_sha256=self._policy.policy_sha256,
                    sequence=last.sequence + 1,
                    record_kind="CHECKPOINT",
                    previous_record_sha256=last.record_sha256,
                    absolute_slot=slot,
                    slot_kind="BASE",
                    source_event_id=None,
                    slot_scheduled_at=scheduled_at(
                        self._policy.starts_at,
                        self._policy.base_sampling_seconds,
                        slot,
                    ),
                    latest_useful_at=None,
                    attempt_status="NOT_ATTEMPTED",
                    observed_at=observed_at,
                    issue_code=issue_code,
                    disposition=disposition,
                    owner_heads=heads,
                    finalization_status=None,
                )
            )

    def record_agent_attention(
        self, *, request_id: str | None = None
    ) -> ContinuityCheckpointV1:
        """Record one Agent-authored next-check window exactly once.

        The request window is replayed from its owner, while its result is
        derived from the first later HypothesisRecord delivered inside or
        after that window.  A caller cannot claim a wake, approval, dispatch,
        capacity result, or synthetic attempt.
        """

        account_policy = self._policy.paper_account
        if account_policy is None:
            raise ContinuityCheckpointError("CONTINUITY_ATTENTION_NOT_INCLUDED")
        logical_agent_id = str(account_policy["logical_agent_id"])
        repository = FileAttentionRepository(
            self._runtime.runtime_root / "attention"
        )
        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if not records:
                raise ContinuityCheckpointError("CONTINUITY_NOT_OPEN")
            last = records[-1]
            if last.record_kind == "FINAL" or last.disposition == "RESTART_REQUIRED":
                raise ContinuityCheckpointError("CONTINUITY_ALREADY_TERMINAL")
            projection = AttentionService(repository).status(logical_agent_id)
            selected_id = request_id or projection.active_request_id
            if not isinstance(selected_id, str) or not selected_id:
                raise ContinuityCheckpointError(
                    "CONTINUITY_ATTENTION_REQUEST_NOT_FOUND"
                )
            if any(record.source_event_id == selected_id for record in records):
                raise ContinuityCheckpointError(
                    "CONTINUITY_ATTENTION_REQUEST_REUSED"
                )
            try:
                request = projection.request(selected_id)
            except Exception as exc:
                raise ContinuityCheckpointError(
                    "CONTINUITY_ATTENTION_REQUEST_NOT_FOUND"
                ) from exc
            scheduled_text = request.earliest
            scheduled = _moment(
                scheduled_text, code="CONTINUITY_ATTENTION_SCHEDULE_INVALID"
            )
            latest = _moment(
                request.latest_useful_at,
                code="CONTINUITY_ATTENTION_LATEST_INVALID",
            )
            observed_at = self._now()
            observed = _moment(observed_at, code="CONTINUITY_CLOCK_INVALID")
            heads = self._owner_heads()
            followup = self._followup_decision(request, heads)
            if followup is None:
                raise ContinuityCheckpointError(
                    "CONTINUITY_ATTENTION_FOLLOWUP_DECISION_NOT_OBSERVED"
                )
            delivered = _moment(
                followup.get("agent_decision_delivered_at"),
                code="CONTINUITY_CYCLE_AGENT_DELIVERY_TIME_INVALID",
            )
            requested = _moment(
                followup.get("requested_at"),
                code="CONTINUITY_CYCLE_REQUEST_TIME_INVALID",
            )
            if requested > observed or delivered > observed:
                raise ContinuityCheckpointError(
                    "CONTINUITY_ATTENTION_FOLLOWUP_DECISION_FROM_FUTURE"
                )
            issue_code: str | None = None
            if requested <= latest:
                attempt_status = "ATTEMPTED_TERMINAL"
            else:
                # This is an observed cadence fact, not a supervisor verdict.
                # Risk, identity, PIT and ledger gates remain elsewhere; a late
                # self-selected check never grants continuity code authority to
                # stop, restart, wake, or approve the trading Goal.
                attempt_status = "NOT_ATTEMPTED"
            slot = absolute_slot(
                self._policy.starts_at,
                self._policy.base_sampling_seconds,
                observed_at,
            )
            if slot > self._last_base_slot(records) + 1:
                if issue_code is not None and issue_code != ABSOLUTE_SLOT_GAP:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_MULTIPLE_ISSUES_UNSUPPORTED"
                    )
                issue_code = ABSOLUTE_SLOT_GAP
            disposition = (
                "CONTINUE" if issue_code is None else self._classify_issue(issue_code)
            )
            try:
                self._compare_owner_heads(last.owner_heads, heads)
            except ContinuityCheckpointError as exc:
                if str(exc) != OWNER_HEAD_DIVERGENCE:
                    raise
                if issue_code is not None and issue_code != OWNER_HEAD_DIVERGENCE:
                    raise ContinuityCheckpointError(
                        "CONTINUITY_MULTIPLE_ISSUES_UNSUPPORTED"
                    )
                issue_code = OWNER_HEAD_DIVERGENCE
                disposition = self._classify_issue(issue_code)
            return self._publish(
                ContinuityCheckpointV1(
                    run_id=self._policy.run_id,
                    policy_sha256=self._policy.policy_sha256,
                    sequence=last.sequence + 1,
                    record_kind="CHECKPOINT",
                    previous_record_sha256=last.record_sha256,
                    absolute_slot=slot,
                    slot_kind="AGENT_ATTENTION",
                    source_event_id=selected_id,
                    slot_scheduled_at=scheduled.isoformat(),
                    latest_useful_at=latest.isoformat(),
                    attempt_status=attempt_status,
                    observed_at=observed_at,
                    issue_code=issue_code,
                    disposition=disposition,
                    owner_heads=heads,
                    finalization_status=None,
                )
            )

    def recover(self) -> ContinuityRecoveryV1:
        """Validate the chain and compare it with freshly replayed owner heads."""

        with exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if not records:
                raise ContinuityCheckpointError("CONTINUITY_NOT_OPEN")
            last = records[-1]
            recovered_at = self._now()
            slot = absolute_slot(
                self._policy.starts_at,
                self._policy.base_sampling_seconds,
                recovered_at,
            )
            try:
                head_status = self._compare_owner_heads(
                    last.owner_heads, self._owner_heads()
                )
                divergence = None
            except ContinuityCheckpointError as exc:
                if str(exc) != OWNER_HEAD_DIVERGENCE:
                    raise
                head_status = "UNCHANGED"
                divergence = OWNER_HEAD_DIVERGENCE

            issue_code: str | None = None
            if last.disposition == "RESTART_REQUIRED":
                action = "RESTART_REQUIRED"
                issue_code = last.issue_code
            elif last.record_kind == "FINAL":
                action = "FINALIZED"
            elif divergence is not None:
                action = self._classify_issue(divergence)
                issue_code = divergence if action == "RESTART_REQUIRED" else None
            elif slot > self._last_base_slot(records) + 1:
                action = self._classify_issue(ABSOLUTE_SLOT_GAP)
                issue_code = ABSOLUTE_SLOT_GAP if action == "RESTART_REQUIRED" else None
            else:
                action = "CONTINUE"
            return ContinuityRecoveryV1(
                run_id=self._policy.run_id,
                policy_sha256=self._policy.policy_sha256,
                recovered_at=recovered_at,
                last_sequence=last.sequence,
                last_record_sha256=last.record_sha256,
                current_absolute_slot=slot,
                action=action,
                owner_head_status=head_status,
                issue_code=issue_code,
            )

    def finalize(self) -> ContinuityCheckpointV1:
        """Finalize continuity coverage while leaving run closure to close-run."""

        with self._mutation_guard(), exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if not records:
                raise ContinuityCheckpointError("CONTINUITY_NOT_OPEN")
            last = records[-1]
            if last.record_kind == "FINAL":
                return last
            if last.disposition == "RESTART_REQUIRED":
                raise ContinuityCheckpointError("CONTINUITY_RESTART_REQUIRED")
            observed_at = self._now()
            now = _moment(observed_at, code="CONTINUITY_CLOCK_INVALID")
            start = _moment(
                self._policy.starts_at, code="CONTINUITY_POLICY_START_INVALID"
            )
            end = start + timedelta(seconds=self._policy.duration_seconds)
            if now < end:
                raise ContinuityCheckpointError("CONTINUITY_FINALIZATION_EARLY")
            final_slot = self._policy.duration_seconds // self._policy.base_sampling_seconds
            observed_slot = absolute_slot(
                self._policy.starts_at,
                self._policy.base_sampling_seconds,
                observed_at,
            )
            if (
                observed_slot > final_slot
                or final_slot > self._last_base_slot(records) + 1
            ):
                raise ContinuityCheckpointError(
                    "CONTINUITY_FINALIZATION_SLOT_GAP_RESTART_REQUIRED"
                )
            heads = self._owner_heads()
            self._compare_owner_heads(last.owner_heads, heads)
            return self._publish(
                ContinuityCheckpointV1(
                    run_id=self._policy.run_id,
                    policy_sha256=self._policy.policy_sha256,
                    sequence=last.sequence + 1,
                    record_kind="FINAL",
                    previous_record_sha256=last.record_sha256,
                    absolute_slot=final_slot,
                    slot_kind="FINAL",
                    source_event_id=None,
                    slot_scheduled_at=scheduled_at(
                        self._policy.starts_at,
                        self._policy.base_sampling_seconds,
                        final_slot,
                    ),
                    latest_useful_at=None,
                    attempt_status="NOT_ATTEMPTED",
                    observed_at=observed_at,
                    issue_code=None,
                    disposition="FINALIZED",
                    owner_heads=heads,
                    finalization_status=FINALIZATION_AWAITING_RUN_CLOSE,
                )
            )

    def load_final(self) -> ContinuityCheckpointV1:
        """Return FINAL only while its frozen fact-owner heads remain current."""

        with exclusive_lock_file(self._lock_path):
            records = self._replay_locked()
            if not records or records[-1].record_kind != "FINAL":
                raise ContinuityCheckpointError("CONTINUITY_FINAL_RECORD_REQUIRED")
            final = records[-1]
            self._compare_owner_heads(final.owner_heads, self._owner_heads())
            return final


__all__ = [
    "ContinuityCheckpointError",
    "FileContinuityCheckpointStore",
    "OWNER_HEAD_DIVERGENCE",
]
