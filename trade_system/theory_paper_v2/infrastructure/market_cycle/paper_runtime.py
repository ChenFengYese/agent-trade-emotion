"""Minimal local-paper composition for one V3.3.2 HYPE trading Agent.

This module is deliberately a thin use-case layer over the existing market
cycle, persistent Agent registry, admitted-data, and paper-ledger owners.  It
has no exchange order transport and cannot turn a paper intent into an
external side effect.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import stat
from typing import Any, Mapping

from ...application.market_cycle.agent_session import AgentSessionService
from ...application.market_cycle.paper import (
    PaperTradingService,
    replay_paper_account,
)
from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from ...domain.market_cycle.attention import AgentRegistry
from ...domain.market_cycle.paper import (
    FundingSettlementModelV1,
    PaperAccountVersionV1,
    PaperContractError,
    PaperCostModelV1,
    PaperExecutionIntentV1,
    StaticNoTransitionComparatorV1,
    StaticNoTransitionEpisodeLinkV1,
)
from ...domain.market_cycle.theory import V332_THEORY_IDENTITY
from ...v32_durable_json import write_once_json
from ..market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    HYPE_OKX_PROFILE_ID,
    build_hype_data_profile_service,
)
from ..market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from ..market_data.raw_capture import FileRawCaptureStore
from .attention_repository import FileAttentionRepository
from .paper_authority import SealedCyclePaperDecisionAuthority
from .paper_intent_mailbox import (
    IssuedPaperExecutionIntentRequest,
    LocalPaperExecutionIntentMailbox,
)
from .paper_ledger import FilePaperLedger
from .funding_scheduler import (
    AdmittedSliceFundingScheduler,
    FundingScheduleResultV1,
    FundingSchedulerError,
)
from .goal_identity import (
    CodexGoalIdentityError,
    current_codex_goal_identity,
)
from .repository import MarketCycleRepositoryError
from .runtime import MarketCycleRuntime


class V332PaperRuntimeError(RuntimeError):
    """The local-paper composition cannot prove an exact required binding."""


def _current_codex_goal_identity() -> str:
    """Translate the shared host identity gate into the paper error owner."""

    try:
        return current_codex_goal_identity()
    except CodexGoalIdentityError as exc:
        raise V332PaperRuntimeError(
            "V332_PAPER_CODEX_THREAD_ID_REQUIRED"
        ) from exc


def _moment(value: str, *, code: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise V332PaperRuntimeError(code) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise V332PaperRuntimeError(code)
    return result


def _decimal(value: object, *, code: str) -> Decimal:
    if not isinstance(value, str):
        raise V332PaperRuntimeError(code)
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise V332PaperRuntimeError(code) from exc
    if not result.is_finite():
        raise V332PaperRuntimeError(code)
    return result


class V332HypePaperRuntime:
    """Compose one policy-bound HYPE paper account inside a market-cycle run.

    The setup cycle is an already sealed/admitted data slice used only to bind
    product economics before the first decision cycle.  Every executable
    intent is later checked against one exact sealed decision cycle, the
    persistent Goal registry, the immutable intent request and the paper head.
    Attention/checkpoint state is independent and never permits or blocks a
    local-paper transaction.
    """

    external_orders_supported = False

    def __init__(self, runtime: MarketCycleRuntime, *, setup_cycle_id: str) -> None:
        if not isinstance(runtime, MarketCycleRuntime):
            raise V332PaperRuntimeError("V332_PAPER_RUNTIME_INVALID")
        policy = runtime.experiment_policy
        if (
            runtime.identity != V332_THEORY_IDENTITY
            or policy is None
            or runtime.run_manifest.experiment_identity != policy.policy_sha256
            or policy.run_id != runtime.run_manifest.run_id
            or policy.venue_id != "OKX"
            or policy.instrument_id != HYPE_OKX_INSTRUMENT_ID
            or policy.market_contract_identity != HYPE_OKX_CONTRACT_IDENTITY
            or policy.data_profile != HYPE_OKX_DATA_PROFILE.market_data_profile
        ):
            raise V332PaperRuntimeError("V332_PAPER_POLICY_IDENTITY_MISMATCH")
        if (
            not policy.local_paper_authorized
            or policy.paper_account is None
            or policy.testnet_authorized
            or policy.live_authorized
            or policy.private_credentials_authorized
            or policy.external_orders_authorized
            or policy.funds_authorized
        ):
            raise V332PaperRuntimeError("V332_PAPER_AUTHORITY_FORBIDDEN")
        if not isinstance(setup_cycle_id, str) or not setup_cycle_id:
            raise V332PaperRuntimeError("V332_PAPER_SETUP_CYCLE_INVALID")

        account_policy = policy.paper_account
        if (
            account_policy["setup_cycle_id"] != setup_cycle_id
            or account_policy["account_mode"] != "LINEAR_PERP"
            or account_policy["base_currency"] != "USDT"
            or account_policy["agent_generation"] != 1
        ):
            raise V332PaperRuntimeError("V332_PAPER_ACCOUNT_POLICY_UNSUPPORTED")
        try:
            cost_model = PaperCostModelV1(**dict(account_policy["cost_model"]))
        except (TypeError, ValueError) as exc:
            raise V332PaperRuntimeError("V332_PAPER_COST_MODEL_INVALID") from exc

        profiles = build_hype_data_profile_service(
            raw_store=FileRawCaptureStore(runtime.runtime_root)
        )
        setup_replay = profiles.replay(
            HYPE_OKX_PROFILE_ID,
            cycle_id=setup_cycle_id,
        )
        if setup_replay.status != "ADMITTED" or setup_replay.data_slice is None:
            raise V332PaperRuntimeError("V332_PAPER_SETUP_SLICE_NOT_ADMITTED")
        setup_slice = setup_replay.data_slice
        if (
            setup_slice.instrument_identity.venue_symbol
            != HYPE_OKX_INSTRUMENT_ID
            or setup_slice.instrument_identity.venue != "OKX"
            or setup_slice.instrument_identity.contract_semantics
            != "LINEAR_PERPETUAL_SWAP"
        ):
            raise V332PaperRuntimeError("V332_PAPER_SETUP_PRODUCT_MISMATCH")

        attention_repository = FileAttentionRepository(
            runtime.runtime_root / "attention"
        )
        self._runtime = runtime
        self._policy = policy
        self._account_policy = account_policy
        self._cost_model = cost_model
        self._profiles = profiles
        self._setup_cycle_id = setup_cycle_id
        self._setup_slice = setup_slice
        self._ledger = FilePaperLedger(runtime.runtime_root / "paper")
        self._attention_repository = attention_repository
        self._sessions = AgentSessionService(attention_repository)

    @property
    def account_id(self) -> str:
        return str(self._account_policy["account_id"])

    @property
    def logical_agent_id(self) -> str:
        return str(self._account_policy["logical_agent_id"])

    @property
    def agent_generation(self) -> int:
        return int(self._account_policy["agent_generation"])

    def _evidence(self, *cycle_ids: str) -> AdmittedAssetSlicePaperMarketEvidence:
        unique = tuple(dict.fromkeys((self._setup_cycle_id, *cycle_ids)))
        return AdmittedAssetSlicePaperMarketEvidence(
            profiles=self._profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_PROFILE_ID,
                    cycle_ids=unique,
                ),
            ),
        )

    def setup(self) -> PaperAccountVersionV1:
        """Bind the host Goal and open its raw-bound LINEAR_PERP account."""

        with self._runtime.mutation_guard():
            return self._setup()

    def _setup(self) -> PaperAccountVersionV1:
        """Run setup inside the caller-held run lifecycle guard."""

        trusted_now = self._runtime.controller_state.trusted_now()
        physical_task_id = _current_codex_goal_identity()
        continuity_nonce = "v332-goal-g1-" + hashlib.sha256(
            canonical_bytes(
                {
                    "schema_id": "agent-trade-emotion.v332-goal-continuity",
                    "schema_version": "1.0.0",
                    "run_id": self._runtime.run_manifest.run_id,
                    "experiment_policy_sha256": self._policy.policy_sha256,
                    "logical_agent_id": self.logical_agent_id,
                    "agent_generation": self.agent_generation,
                    "physical_goal_id": physical_task_id,
                }
            )
        ).hexdigest()
        existing_projection = self._sessions.status(self.logical_agent_id)
        existing_registry = existing_projection.registry
        existing_records = self._ledger.load_records(self.account_id)
        if existing_registry is not None:
            if (
                existing_registry.logical_agent_id != self.logical_agent_id
                or existing_registry.symbol != HYPE_OKX_INSTRUMENT_ID
                or existing_registry.generation != self.agent_generation
                or existing_registry.physical_task_id != physical_task_id
                or existing_registry.continuity_nonce != continuity_nonce
            ):
                raise V332PaperRuntimeError(
                    "V332_PAPER_EXISTING_GOAL_BINDING_MISMATCH"
                )
            if existing_records:
                return self._require_account()
            registered_at = existing_registry.registered_at
        elif existing_records:
            raise V332PaperRuntimeError("V332_PAPER_ACCOUNT_WITHOUT_GOAL")
        else:
            registered_at = trusted_now
        opened_at = trusted_now
        registered = _moment(
            registered_at, code="V332_PAPER_REGISTERED_AT_INVALID"
        )
        opened = _moment(opened_at, code="V332_PAPER_OPENED_AT_INVALID")
        if (
            registered > opened
            or opened < _moment(
                self._setup_slice.sealed_at,
                code="V332_PAPER_SETUP_SLICE_TIME_INVALID",
            )
            or opened < _moment(
                self._policy.starts_at,
                code="V332_PAPER_POLICY_START_INVALID",
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_SETUP_TIME_ORDER_INVALID")

        evidence = self._evidence()
        instrument_spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=opened_at,
        )
        if (
            instrument_spec is None
            or instrument_spec.parameter_status != "OBSERVED_RAW_BOUND"
            or not evidence.verifies_instrument_spec(
                instrument_spec, available_by=opened_at
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_INSTRUMENT_SPEC_UNVERIFIED")

        registry = AgentRegistry(
            logical_agent_id=self.logical_agent_id,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            generation=self.agent_generation,
            continuity_nonce=continuity_nonce,
            physical_task_id=physical_task_id,
            status="ACTIVE",
            registered_at=registered_at,
        )
        # All policy, time, data, product and model checks above are read-only.
        # Registration is idempotent, so an interrupted setup can be retried.
        self._sessions.register(registry)
        paper = PaperTradingService(
            self._ledger,
            cost_models=(self._cost_model,),
            market_evidence=evidence,
            carry_evidence=evidence,
            require_execution_intent=True,
            max_position_notional=self._account_policy[
                "max_position_notional"
            ],
        )
        account = paper.open_account(
            account_id=self.account_id,
            account_mode="LINEAR_PERP",
            owner_logical_agent_id=self.logical_agent_id,
            owner_agent_generation=self.agent_generation,
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage=str(self._account_policy["max_leverage"]),
            initial_balance=str(self._account_policy["initial_balance"]),
            opened_at=opened_at,
            instrument_spec=instrument_spec,
        )
        self._require_account(account)
        return account

    def _policy_end_at(self) -> str:
        return (
            _moment(self._policy.starts_at, code="V332_PAPER_POLICY_START_INVALID")
            + timedelta(seconds=self._policy.duration_seconds)
        ).isoformat()

    def _paper_action_hard_stop(self, decision_cycle_id: str) -> str:
        try:
            plan = self._runtime.repository.load_artifact(
                decision_cycle_id, "BehaviorPlan"
            )
        except MarketCycleRepositoryError as exc:
            raise V332PaperRuntimeError("V332_PAPER_PLAN_NOT_SEALED") from exc
        outcome_due_at = plan.get("outcome_due_at")
        if not isinstance(outcome_due_at, str):
            raise V332PaperRuntimeError("V332_PAPER_PLAN_TIME_INVALID")
        return min(
            (outcome_due_at, self._policy_end_at()),
            key=lambda value: _moment(
                value, code="V332_PAPER_ACTION_HARD_STOP_INVALID"
            ),
        )

    def _require_action_window(
        self,
        decision_cycle_id: str,
        *,
        valid_until: str | None = None,
        received_at: str | None = None,
    ) -> str:
        hard_stop = self._paper_action_hard_stop(decision_cycle_id)
        trusted_now = self._runtime.controller_state.trusted_now()
        now = _moment(trusted_now, code="V332_PAPER_TRUSTED_CLOCK_INVALID")
        stop = _moment(hard_stop, code="V332_PAPER_ACTION_HARD_STOP_INVALID")
        if now >= stop:
            raise V332PaperRuntimeError("V332_PAPER_ACTION_WINDOW_EXPIRED")
        if valid_until is not None and _moment(
            valid_until, code="V332_PAPER_ACTION_WINDOW_INVALID"
        ) > stop:
            raise V332PaperRuntimeError("V332_PAPER_ACTION_WINDOW_EXCEEDS_HARD_STOP")
        if received_at is not None and _moment(
            received_at, code="V332_PAPER_RECEIPT_TIME_INVALID"
        ) >= stop:
            raise V332PaperRuntimeError("V332_PAPER_ACTION_RECEIVED_AFTER_HARD_STOP")
        return trusted_now

    @staticmethod
    def _recover_issued_at(
        request_path: Path,
        *,
        decision_cycle_id: str,
        valid_until: str,
        invalid_code: str,
    ) -> str | None:
        """Recover create-once request chronology without trusting a caller.

        A restarted issuer must reproduce the existing immutable document, so
        it reuses only the issued_at already sealed beside the same cycle and
        requested expiry.  The owning mailbox performs the complete contract
        and canonical-file validation when issue_request is called below.
        """

        if not request_path.exists():
            return None
        try:
            document = loads_json_strict(request_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise V332PaperRuntimeError(invalid_code) from exc
        issued_at = document.get("issued_at")
        if (
            document.get("cycle_id") != decision_cycle_id
            or document.get("valid_until") != valid_until
            or not isinstance(issued_at, str)
        ):
            raise V332PaperRuntimeError(invalid_code)
        _moment(issued_at, code=invalid_code)
        return issued_at

    def _require_account(
        self, account: PaperAccountVersionV1 | None = None
    ) -> PaperAccountVersionV1:
        records = self._ledger.load_records(self.account_id)
        if not records:
            raise V332PaperRuntimeError("V332_PAPER_ACCOUNT_NOT_OPENED")
        replayed = replay_paper_account(records) if account is None else account
        if (
            replayed.account_id != self.account_id
            or replayed.account_mode != "LINEAR_PERP"
            or replayed.owner_logical_agent_id != self.logical_agent_id
            or replayed.owner_agent_generation != self.agent_generation
            or replayed.base_currency != "USDT"
            or replayed.permitted_symbol != HYPE_OKX_INSTRUMENT_ID
            or replayed.initial_balance
            != str(self._account_policy["initial_balance"])
            or replayed.max_leverage != str(self._account_policy["max_leverage"])
        ):
            raise V332PaperRuntimeError("V332_PAPER_ACCOUNT_POLICY_MISMATCH")
        evidence = self._evidence()
        if not evidence.verifies_instrument_spec(
            replayed.instrument_spec,
            available_by=replayed.last_fact_at,
        ):
            raise V332PaperRuntimeError("V332_PAPER_ACCOUNT_SPEC_DRIFT")
        registry = self._sessions.current(self.logical_agent_id)
        if (
            registry.symbol != HYPE_OKX_INSTRUMENT_ID
            or registry.generation != self.agent_generation
        ):
            raise V332PaperRuntimeError("V332_PAPER_AGENT_GENERATION_DRIFT")
        return replayed

    def _registered_goal_identity(self) -> str:
        """Return the one active persistent Goal identity from its fact owner."""

        registry = self._sessions.current(self.logical_agent_id)
        if (
            registry.status not in {"ACTIVE", "IDLE"}
            or registry.generation != self.agent_generation
            or registry.symbol != HYPE_OKX_INSTRUMENT_ID
            or not isinstance(registry.physical_task_id, str)
            or not registry.physical_task_id
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_REGISTERED_GOAL_IDENTITY_INVALID"
            )
        return registry.physical_task_id

    def _require_current_goal_caller(self) -> str:
        """Prove this process is the Goal bound to the durable registry."""

        current_goal_id = _current_codex_goal_identity()
        if self._registered_goal_identity() != current_goal_id:
            raise V332PaperRuntimeError("V332_PAPER_CALLER_GOAL_MISMATCH")
        return current_goal_id

    @staticmethod
    def _read_canonical_document(
        path: Path, *, code: str
    ) -> tuple[dict[str, Any], bytes]:
        """Read one immutable regular JSON document without trusting its path."""

        try:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size <= 0
                or metadata.st_size > 16 * 1024 * 1024
            ):
                raise ValueError("unsafe document")
            raw = path.read_bytes()
            if len(raw) != metadata.st_size:
                raise ValueError("short document read")
            document = loads_json_strict(raw)
            canonical = canonical_bytes(document)
            if raw not in {canonical, canonical + b"\n"}:
                raise ValueError("non-canonical document")
        except (CanonicalContractError, OSError, ValueError) as exc:
            raise V332PaperRuntimeError(code) from exc
        return document, raw

    def _decision_goal_binding_path(self, decision_cycle_id: str) -> Path:
        return (
            self._runtime.runtime_root
            / "cycles"
            / decision_cycle_id
            / "transport"
            / "decision-goal-binding.json"
        )

    def _decision_goal_binding_document(
        self,
        decision_cycle_id: str,
        *,
        intent_request_sha256: str,
        bound_at: str,
    ) -> dict[str, Any]:
        """Rebuild the exact immutable decision-to-Goal provenance binding.

        The market-cycle repository proves the PIT snapshot and its raw refs;
        the transport files prove which bytes the Agent received and returned;
        and the Agent registry proves which persistent Goal owns this account.
        No controller Worker dispatch or supervisor receipt participates.
        """

        if (
            not isinstance(intent_request_sha256, str)
            or len(intent_request_sha256) != 64
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_INVALID"
            )
        registry = self._sessions.current(self.logical_agent_id)
        physical_goal_id = self._registered_goal_identity()
        try:
            cycle_request = self._runtime.repository.load_request(
                decision_cycle_id
            )
            state = self._runtime.repository.load_state(decision_cycle_id)
            snapshot = self._runtime.repository.load_artifact(
                decision_cycle_id, "InputSnapshot"
            )
            hypothesis = self._runtime.repository.load_artifact(
                decision_cycle_id, "HypothesisRecord"
            )
            plan = self._runtime.repository.load_artifact(
                decision_cycle_id, "BehaviorPlan"
            )
        except MarketCycleRepositoryError as exc:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_SOURCE_INVALID"
            ) from exc
        references = {item.artifact_type: item for item in state.artifact_refs}
        if not {"InputSnapshot", "HypothesisRecord", "BehaviorPlan"}.issubset(
            references
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_SOURCE_INVALID"
            )
        cycle_root = (
            self._runtime.runtime_root / "cycles" / decision_cycle_id
        )
        request_document, request_raw = self._read_canonical_document(
            cycle_root / "request.json",
            code="V332_PAPER_DECISION_GOAL_SOURCE_INVALID",
        )
        agent_request, agent_request_raw = self._read_canonical_document(
            cycle_root / "transport" / "agent-request.json",
            code="V332_PAPER_DECISION_GOAL_SOURCE_INVALID",
        )
        delivery_path_value = hypothesis.get("agent_delivery_path")
        if delivery_path_value != "transport/agent-delivery.json":
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_SOURCE_INVALID"
            )
        agent_delivery, agent_delivery_raw = self._read_canonical_document(
            cycle_root / "transport" / "agent-delivery.json",
            code="V332_PAPER_DECISION_GOAL_SOURCE_INVALID",
        )
        artifact_documents: dict[str, tuple[dict[str, Any], bytes]] = {}
        for artifact_type in (
            "InputSnapshot",
            "HypothesisRecord",
            "BehaviorPlan",
        ):
            reference = references[artifact_type]
            artifact_documents[artifact_type] = self._read_canonical_document(
                cycle_root / reference.path,
                code="V332_PAPER_DECISION_GOAL_SOURCE_INVALID",
            )
            document, raw = artifact_documents[artifact_type]
            if (
                document
                != {
                    "InputSnapshot": snapshot,
                    "HypothesisRecord": hypothesis,
                    "BehaviorPlan": plan,
                }[artifact_type]
                or len(raw) != reference.size_bytes
                or hashlib.sha256(raw).hexdigest() != reference.sha256
            ):
                raise V332PaperRuntimeError(
                    "V332_PAPER_DECISION_GOAL_SOURCE_INVALID"
                )

        packet = agent_request.get("packet")
        packet_sha256 = agent_request.get("packet_sha256")
        registry_identity_fields = (
            "logical_agent_id",
            "symbol",
            "generation",
            "continuity_nonce",
            "physical_task_id",
            "registered_at",
            "prior_continuity_nonce",
            "resume_capsule_ref",
        )
        registry_identity = {
            field: registry.to_dict()[field] for field in registry_identity_fields
        }
        matching_registry_events = []
        for event in self._attention_repository.replay(self.logical_agent_id):
            event_registry = event.payload.get("registry")
            if not isinstance(event_registry, Mapping):
                continue
            if {
                field: event_registry.get(field)
                for field in registry_identity_fields
            } == registry_identity:
                matching_registry_events.append(event)
        if len(matching_registry_events) != 1:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_REGISTRY_INVALID"
            )
        registry_event = matching_registry_events[0]
        try:
            bound = _moment(
                bound_at, code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID"
            )
            registered = _moment(
                registry.registered_at,
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
            decision_at = _moment(
                str(hypothesis.get("decision_at")),
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
            delivered_at = _moment(
                str(hypothesis.get("agent_delivered_at")),
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
            hypothesis_sealed_at = _moment(
                str(hypothesis.get("sealed_at")),
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
            plan_sealed_at = _moment(
                str(plan.get("sealed_at")),
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
            hard_stop = _moment(
                self._paper_action_hard_stop(decision_cycle_id),
                code="V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID",
            )
        except (TypeError, ValueError) as exc:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_TIME_INVALID"
            ) from exc
        decision_sha256 = hypothesis.get("agent_decision_sha256")
        input_reference = references["InputSnapshot"]
        if (
            request_document != cycle_request.to_dict()
            or cycle_request.instrument_id != HYPE_OKX_INSTRUMENT_ID
            or cycle_request.contract_identity != HYPE_OKX_CONTRACT_IDENTITY
            or not isinstance(packet, Mapping)
            or packet.get("cycle_id") != decision_cycle_id
            or packet.get("input_snapshot") != snapshot
            or packet.get("input_snapshot_ref") != input_reference.to_dict()
            or packet_sha256
            != hashlib.sha256(canonical_bytes(packet)).hexdigest()
            or hypothesis.get("agent_request_sha256") != packet_sha256
            or agent_delivery.get("cycle_id") != decision_cycle_id
            or agent_delivery.get("request_sha256") != packet_sha256
            or agent_delivery.get("decision_sha256") != decision_sha256
            or agent_delivery.get("physical_goal_id") != physical_goal_id
            or hashlib.sha256(agent_delivery_raw).hexdigest()
            != hypothesis.get("agent_delivery_sha256")
            or plan.get("cycle_id") != decision_cycle_id
            or plan.get("agent_request_sha256") != packet_sha256
            or plan.get("agent_delivery_sha256")
            != hypothesis.get("agent_delivery_sha256")
            or plan.get("agent_decision_sha256") != decision_sha256
            or not registered
            <= decision_at
            <= delivered_at
            <= hypothesis_sealed_at
            <= plan_sealed_at
            <= bound
            < hard_stop
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_SOURCE_INVALID"
            )
        return {
            "schema_id": "agent-trade-emotion.v332-decision-goal-binding",
            "schema_version": "1.0.0",
            "run_id": self._runtime.run_manifest.run_id,
            "cycle_id": decision_cycle_id,
            "logical_agent_id": self.logical_agent_id,
            "agent_generation": self.agent_generation,
            "physical_goal_id": physical_goal_id,
            "continuity_nonce_sha256": hashlib.sha256(
                registry.continuity_nonce.encode("utf-8")
            ).hexdigest(),
            "registry_event_revision": registry_event.revision,
            "registry_event_sha256": registry_event.event_sha256,
            "cycle_request_relative_path": "request.json",
            "cycle_request_sha256": hashlib.sha256(request_raw).hexdigest(),
            "input_snapshot_relative_path": input_reference.path,
            "input_snapshot_sha256": input_reference.sha256,
            "agent_request_relative_path": "transport/agent-request.json",
            "agent_request_document_sha256": hashlib.sha256(
                agent_request_raw
            ).hexdigest(),
            "agent_request_packet_sha256": str(packet_sha256),
            "agent_delivery_relative_path": "transport/agent-delivery.json",
            "agent_delivery_sha256": hashlib.sha256(
                agent_delivery_raw
            ).hexdigest(),
            "hypothesis_record_relative_path": references[
                "HypothesisRecord"
            ].path,
            "hypothesis_record_sha256": references[
                "HypothesisRecord"
            ].sha256,
            "behavior_plan_relative_path": references["BehaviorPlan"].path,
            "behavior_plan_sha256": references["BehaviorPlan"].sha256,
            "decision_sha256": str(decision_sha256),
            "intent_request_relative_path": (
                "transport/paper-execution-intent-request.json"
            ),
            "intent_request_sha256": intent_request_sha256,
            "bound_at": bound_at,
        }

    def _seal_decision_goal_binding(
        self,
        decision_cycle_id: str,
        *,
        intent_request_sha256: str,
        bound_at: str,
    ) -> tuple[Mapping[str, Any], str]:
        document = self._decision_goal_binding_document(
            decision_cycle_id,
            intent_request_sha256=intent_request_sha256,
            bound_at=bound_at,
        )
        path = self._decision_goal_binding_path(decision_cycle_id)
        try:
            write_once_json(path, document)
        except (CanonicalContractError, OSError) as exc:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_FAILED"
            ) from exc
        sealed, raw = self._read_canonical_document(
            path, code="V332_PAPER_DECISION_GOAL_BINDING_INVALID"
        )
        if sealed != document:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_CONFLICT"
            )
        return sealed, hashlib.sha256(raw).hexdigest()

    def _load_decision_goal_binding(
        self,
        decision_cycle_id: str,
        *,
        intent_request_sha256: str,
    ) -> tuple[Mapping[str, Any], str]:
        path = self._decision_goal_binding_path(decision_cycle_id)
        sealed, raw = self._read_canonical_document(
            path, code="V332_PAPER_DECISION_GOAL_BINDING_INVALID"
        )
        bound_at = sealed.get("bound_at")
        if not isinstance(bound_at, str):
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_INVALID"
            )
        expected = self._decision_goal_binding_document(
            decision_cycle_id,
            intent_request_sha256=intent_request_sha256,
            bound_at=bound_at,
        )
        if sealed != expected:
            raise V332PaperRuntimeError(
                "V332_PAPER_DECISION_GOAL_BINDING_MISMATCH"
            )
        return sealed, hashlib.sha256(raw).hexdigest()

    def _authority(
        self, decision_cycle_id: str
    ) -> SealedCyclePaperDecisionAuthority:
        return SealedCyclePaperDecisionAuthority(
            sessions=self._sessions,
            cycle_repository=self._runtime.repository,
            agent_cycle_bindings={
                self.logical_agent_id: (decision_cycle_id,)
            },
        )

    def _issue_execution_intent_request(
        self,
        mailbox: LocalPaperExecutionIntentMailbox,
        *,
        decision_cycle_id: str,
        valid_until: str,
    ) -> IssuedPaperExecutionIntentRequest:
        """Freeze the mailbox-owned request after the BehaviorPlan is sealed."""

        account = self._require_account()
        physical_task_id = self._registered_goal_identity()
        expected_root = (
            self._runtime.runtime_root / "cycles" / decision_cycle_id / "transport"
        )
        if (
            not isinstance(mailbox, LocalPaperExecutionIntentMailbox)
            or mailbox.intent_request_path(decision_cycle_id)
            != expected_root / "paper-execution-intent-request.json"
        ):
            raise V332PaperRuntimeError("V332_PAPER_INTENT_MAILBOX_SCOPE_MISMATCH")
        request_path = mailbox.intent_request_path(decision_cycle_id)
        recovered_issued_at = self._recover_issued_at(
            request_path,
            decision_cycle_id=decision_cycle_id,
            valid_until=valid_until,
            invalid_code="V332_PAPER_INTENT_REQUEST_INVALID",
        )
        if recovered_issued_at is None:
            issued_at = self._require_action_window(
                decision_cycle_id,
                valid_until=valid_until,
            )
        else:
            issued_at = recovered_issued_at
        try:
            hypothesis = self._runtime.repository.load_artifact(
                decision_cycle_id, "HypothesisRecord"
            )
            plan = self._runtime.repository.load_artifact(
                decision_cycle_id, "BehaviorPlan"
            )
        except MarketCycleRepositoryError as exc:
            raise V332PaperRuntimeError("V332_PAPER_PLAN_NOT_SEALED") from exc
        if (
            account.version < 1
            or not isinstance(hypothesis.get("agent_decision_sha256"), str)
            or plan.get("cycle_id") != decision_cycle_id
            or plan.get("agent_decision_sha256")
            != hypothesis.get("agent_decision_sha256")
            or _moment(issued_at, code="V332_PAPER_INTENT_REQUEST_TIME_INVALID")
            < _moment(
                str(plan.get("sealed_at")),
                code="V332_PAPER_PLAN_TIME_INVALID",
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_INTENT_REQUEST_INVALID")
        return mailbox.issue_request(
            decision_cycle_id,
            logical_agent_id=self.logical_agent_id,
            agent_generation=self.agent_generation,
            physical_task_id=physical_task_id,
            decision_sha256=str(hypothesis["agent_decision_sha256"]),
            issued_at=issued_at,
            valid_until=valid_until,
        )

    def _intent_mailbox(self) -> LocalPaperExecutionIntentMailbox:
        return LocalPaperExecutionIntentMailbox(
            self._runtime.runtime_root / "cycles",
            clock=self._runtime.controller_state.trusted_now,
        )

    def _submit_received_intent(
        self,
        execution_intent: PaperExecutionIntentV1,
        *,
        received_at: str,
    ) -> PaperAccountVersionV1:
        """Apply one verified Agent intent to the local paper ledger only."""

        account = self._require_account()
        if not isinstance(execution_intent, PaperExecutionIntentV1):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_INTENT_INVALID")
        records = self._ledger.load_records(self.account_id)
        prior_intents = tuple(
            record.payload.get("execution_intent")
            for record in records
            if record.event_type in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}
            and isinstance(record.payload.get("execution_intent"), Mapping)
            and record.payload["execution_intent"].get("intent_id")
            == execution_intent.intent_id
        )
        if prior_intents:
            if len(prior_intents) != 1 or prior_intents[0] != execution_intent.to_dict():
                raise V332PaperRuntimeError("V332_PAPER_EXECUTION_INTENT_CONFLICT")
            return account
        command = execution_intent.command
        commands = (
            ()
            if command is None
            else (
                execution_intent.bracket.commands
                if execution_intent.bracket is not None
                else (command,)
            )
        )
        if (
            execution_intent.account_id != self.account_id
            or execution_intent.logical_agent_id != self.logical_agent_id
            or execution_intent.agent_generation != self.agent_generation
            or execution_intent.expected_account_version != account.version
            or execution_intent.symbol != HYPE_OKX_INSTRUMENT_ID
            or any(
                item.cost_model_id != self._cost_model.model_id
                for item in commands
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_POLICY_MISMATCH")
        if (
            not records
            or records[-1].record_sha256
            != execution_intent.ledger_head_record_sha256
        ):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_LEDGER_HEAD_STALE")
        risk = execution_intent.risk_budget
        if (
            _decimal(risk.get("maximum_loss"), code="V332_PAPER_RISK_INVALID")
            > _decimal(
                self._account_policy["max_decision_loss"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
            or _decimal(risk.get("notional_cap"), code="V332_PAPER_RISK_INVALID")
            > _decimal(
                self._account_policy["max_position_notional"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
            or _decimal(
                risk.get("max_observed_drawdown"),
                code="V332_PAPER_RISK_INVALID",
            )
            > _decimal(
                self._account_policy["max_observed_drawdown"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_RISK_POLICY_EXCEEDED")

        self._require_recomputed_target_risk(account, execution_intent)

        evidence = self._evidence(execution_intent.decision_cycle_id)
        paper = PaperTradingService(
            self._ledger,
            cost_models=(self._cost_model,),
            decision_authority=self._authority(
                execution_intent.decision_cycle_id
            ),
            market_evidence=evidence,
            carry_evidence=evidence,
            require_execution_intent=True,
            max_position_notional=self._account_policy[
                "max_position_notional"
            ],
        )
        return paper.submit_intent(
            execution_intent,
            received_at=received_at,
        )

    def _validate_received_intent(
        self,
        execution_intent: PaperExecutionIntentV1,
        *,
        received_at: str,
    ) -> None:
        """Prove policy, risk and authority before either owner is mutated."""

        account = self._require_account()
        if not isinstance(execution_intent, PaperExecutionIntentV1):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_INTENT_INVALID")
        records = self._ledger.load_records(self.account_id)
        command = execution_intent.command
        commands = (
            ()
            if command is None
            else (
                execution_intent.bracket.commands
                if execution_intent.bracket is not None
                else (command,)
            )
        )
        if (
            execution_intent.account_id != self.account_id
            or execution_intent.logical_agent_id != self.logical_agent_id
            or execution_intent.agent_generation != self.agent_generation
            or execution_intent.expected_account_version != account.version
            or execution_intent.symbol != HYPE_OKX_INSTRUMENT_ID
            or any(
                item.cost_model_id != self._cost_model.model_id
                for item in commands
            )
            or not records
            or records[-1].record_sha256
            != execution_intent.ledger_head_record_sha256
        ):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_POLICY_MISMATCH")
        if not (
            _moment(
                execution_intent.authored_at,
                code="V332_PAPER_INTENT_TIME_INVALID",
            )
            <= _moment(received_at, code="V332_PAPER_RECEIPT_TIME_INVALID")
            <= _moment(
                execution_intent.valid_until,
                code="V332_PAPER_INTENT_TIME_INVALID",
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_EXECUTION_INTENT_EXPIRED")
        risk = execution_intent.risk_budget
        if (
            _decimal(risk.get("maximum_loss"), code="V332_PAPER_RISK_INVALID")
            > _decimal(
                self._account_policy["max_decision_loss"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
            or _decimal(
                risk.get("notional_cap"), code="V332_PAPER_RISK_INVALID"
            )
            > _decimal(
                self._account_policy["max_position_notional"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
            or _decimal(
                risk.get("max_observed_drawdown"),
                code="V332_PAPER_RISK_INVALID",
            )
            > _decimal(
                self._account_policy["max_observed_drawdown"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
        ):
            raise V332PaperRuntimeError("V332_PAPER_RISK_POLICY_EXCEEDED")
        self._require_recomputed_target_risk(account, execution_intent)

        authority = self._authority(execution_intent.decision_cycle_id)
        # Attention has not been persisted yet. Validate authority against the
        # exact prospective request through a temporary read-only service is
        # impossible because authority intentionally reads the fact owner.
        # Every authority-independent invariant is therefore proven here; the
        # exact attention/decision binding is separately validated above and
        # the final append remains the only stateful authority check.
        if (
            authority.current_generation(execution_intent.logical_agent_id)
            != execution_intent.agent_generation
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_EXECUTION_AUTHORITY_INVALID"
            )

    def _require_recomputed_target_risk(
        self,
        account: PaperAccountVersionV1,
        execution_intent: PaperExecutionIntentV1,
    ) -> None:
        """Recompute exposure from admitted MARK and raw product economics."""

        replay = self._profiles.replay(
            HYPE_OKX_PROFILE_ID,
            cycle_id=execution_intent.decision_cycle_id,
        )
        if replay.status != "ADMITTED" or replay.data_slice is None:
            raise V332PaperRuntimeError("V332_PAPER_RISK_MARK_NOT_ADMITTED")
        mark_value = replay.data_slice.core_observations.get("mark_price", {}).get(
            "value"
        )
        mark = _decimal(mark_value, code="V332_PAPER_RISK_MARK_INVALID")
        command = execution_intent.command
        prices = [mark]
        if command is not None:
            for candidate in (command.limit_price, command.trigger_price):
                if candidate is not None:
                    prices.append(
                        _decimal(
                            candidate,
                            code="V332_PAPER_RISK_COMMAND_PRICE_INVALID",
                        )
                    )
        conservative_price = max(prices)
        target_quantity = _decimal(
            execution_intent.target_state.get("signed_quantity"),
            code="V332_PAPER_RISK_TARGET_INVALID",
        )
        pre_quantity = _decimal(
            execution_intent.pre_state.get("signed_quantity"),
            code="V332_PAPER_RISK_PRE_STATE_INVALID",
        )
        actual_position = next(
            (
                item
                for item in account.positions
                if item.symbol == execution_intent.symbol
            ),
            None,
        )
        actual_quantity = Decimal(
            "0" if actual_position is None else actual_position.quantity
        )
        if pre_quantity != actual_quantity:
            raise V332PaperRuntimeError("V332_PAPER_RISK_PRE_STATE_STALE")
        increases_exposure = abs(target_quantity) > abs(actual_quantity)
        if (
            target_quantity < min(actual_quantity, Decimal("0"))
            and execution_intent.bracket is None
        ):
            # A newly increased net short remains forbidden unless the exact
            # intent also carries the verified atomic protective bracket.
            raise V332PaperRuntimeError(
                "V332_PAPER_UNBOUNDED_SHORT_RISK_FORBIDDEN"
            )
        multiplier = Decimal(account.instrument_spec.contract_multiplier)
        target_notional = abs(target_quantity) * multiplier * conservative_price
        intent_notional_cap = _decimal(
            execution_intent.risk_budget.get("notional_cap"),
            code="V332_PAPER_RISK_INVALID",
        )
        policy_notional_cap = _decimal(
            self._account_policy["max_position_notional"],
            code="V332_PAPER_POLICY_RISK_INVALID",
        )
        if target_notional > min(intent_notional_cap, policy_notional_cap):
            raise V332PaperRuntimeError(
                "V332_PAPER_RECOMPUTED_NOTIONAL_CAP_EXCEEDED"
            )
        if increases_exposure and execution_intent.bracket is not None:
            bracket = execution_intent.bracket
            entry = bracket.entry
            stop = bracket.protective_stop
            quantity = _decimal(
                entry.quantity,
                code="V332_PAPER_BRACKET_QUANTITY_INVALID",
            )
            entry_price = _decimal(
                entry.limit_price,
                code="V332_PAPER_BRACKET_ENTRY_PRICE_INVALID",
            )
            stop_price = _decimal(
                stop.trigger_price,
                code="V332_PAPER_BRACKET_STOP_PRICE_INVALID",
            )
            impact_rate = _decimal(
                self._cost_model.market_impact_bps,
                code="V332_PAPER_BRACKET_IMPACT_INVALID",
            ) / Decimal("10000")
            fee_rate = _decimal(
                self._cost_model.taker_fee_bps,
                code="V332_PAPER_BRACKET_FEE_INVALID",
            ) / Decimal("10000")
            entry_execution = entry_price * (
                Decimal("1") + impact_rate
                if entry.side == "BUY"
                else Decimal("1") - impact_rate
            )
            stop_execution = stop_price * (
                Decimal("1") + impact_rate
                if stop.side == "BUY"
                else Decimal("1") - impact_rate
            )
            price_loss_per_unit = (
                stop_execution - entry_execution
                if entry.side == "SELL"
                else entry_execution - stop_execution
            )
            modeled_price_loss = (
                max(price_loss_per_unit, Decimal("0"))
                * quantity
                * multiplier
            )
            modeled_fees = (
                (entry_execution + stop_execution)
                * quantity
                * multiplier
                * fee_rate
            )
            modeled_loss = modeled_price_loss + modeled_fees
            maximum_loss = _decimal(
                execution_intent.risk_budget.get("maximum_loss"),
                code="V332_PAPER_RISK_INVALID",
            )
            policy_loss_cap = _decimal(
                self._account_policy["max_decision_loss"],
                code="V332_PAPER_POLICY_RISK_INVALID",
            )
            # This is a frozen local-paper stress using the declared entry and
            # stop plus the existing fee/impact model.  It is not a claim that
            # a real stop has a hard maximum loss under gaps or missing fills.
            if modeled_loss > min(maximum_loss, policy_loss_cap):
                raise V332PaperRuntimeError(
                    "V332_PAPER_BRACKET_MODELED_LOSS_CAP_EXCEEDED"
                )
        elif increases_exposure:
            maximum_loss = _decimal(
                execution_intent.risk_budget.get("maximum_loss"),
                code="V332_PAPER_RISK_INVALID",
            )
            # No verified stop-fill model exists in the first probe. Treat the
            # full target notional as the only defensible loss stress bound.
            if target_notional > maximum_loss:
                raise V332PaperRuntimeError(
                    "V332_PAPER_FULL_NOTIONAL_STRESS_CAP_EXCEEDED"
                )

    def _advance_funding(self, *, cycle_id: str) -> FundingScheduleResultV1:
        """Advance the latest strictly bracketed funding window in one slice.

        The caller supplies only the admitted cycle identity.  The newest
        official settlement in that immutable slice is the after-boundary;
        one microsecond before it is therefore the latest time the scheduler
        may try to cover without predicting a rate or accepting a caller
        chosen window.  The scheduler still proves the before-boundary,
        enumerates every in-window event and preserves UNKNOWN/PARTIAL when
        the admitted evidence is insufficient.
        """

        account = self._require_account()
        replay = self._profiles.replay(HYPE_OKX_PROFILE_ID, cycle_id=cycle_id)
        if replay.status != "ADMITTED" or replay.data_slice is None:
            raise V332PaperRuntimeError("V332_PAPER_FUNDING_SLICE_NOT_ADMITTED")
        if (
            self._cost_model.effective_from is None
            or self._cost_model.effective_to is None
        ):
            raise V332PaperRuntimeError("V332_PAPER_FUNDING_MODEL_WINDOW_UNKNOWN")
        funding = replay.data_slice.optional_observations.get(
            "okx_funding_rate_history"
        )
        if funding is None:
            return FundingScheduleResultV1(
                status="UNKNOWN",
                reason="OFFICIAL_FUNDING_HISTORY_UNAVAILABLE",
                observed_event_count=None,
                advance_id=None,
                account_version=account.version,
            )
        raw_rows = funding.get("value")
        if not isinstance(raw_rows, (tuple, list)) or not raw_rows:
            return FundingScheduleResultV1(
                status="UNKNOWN",
                reason="OFFICIAL_FUNDING_HISTORY_INVALID",
                observed_event_count=None,
                advance_id=None,
                account_version=account.version,
            )
        boundaries: list[datetime] = []
        seen: set[str] = set()
        for item in raw_rows:
            if not isinstance(item, Mapping):
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "OFFICIAL_FUNDING_HISTORY_INVALID",
                    None,
                    None,
                    account.version,
                )
            effective_at = item.get("provider_as_of")
            if (
                item.get("instrument_id") != account.permitted_symbol
                or not isinstance(effective_at, str)
                or effective_at in seen
            ):
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "OFFICIAL_FUNDING_HISTORY_DUPLICATE_OR_MISMATCHED",
                    None,
                    None,
                    account.version,
                )
            try:
                boundary = _moment(
                    effective_at,
                    code="V332_PAPER_FUNDING_EVENT_TIME_INVALID",
                )
            except V332PaperRuntimeError:
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "OFFICIAL_FUNDING_HISTORY_INVALID",
                    None,
                    None,
                    account.version,
                )
            seen.add(effective_at)
            boundaries.append(boundary)

        coverage_end = max(boundaries) - timedelta(microseconds=1)
        records = self._ledger.load_records(account.account_id)
        opened_at = _moment(
            records[0].occurred_at,
            code="V332_PAPER_FUNDING_ACCOUNT_START_INVALID",
        )
        if coverage_end <= opened_at:
            return FundingScheduleResultV1(
                status="PARTIAL",
                reason="LATEST_OFFICIAL_SETTLEMENT_NOT_FORWARD_OF_ACCOUNT",
                observed_event_count=None,
                advance_id=None,
                account_version=account.version,
            )
        if (
            account.funding_coverage_status == "COMPLETE"
            and account.funding_coverage_end_at is not None
            and coverage_end
            <= _moment(
                account.funding_coverage_end_at,
                code="V332_PAPER_FUNDING_COVERAGE_TIME_INVALID",
            )
        ):
            prior_advance = next(
                (
                    record
                    for record in reversed(records)
                    if record.event_type == "FUNDING_COVERAGE_ADVANCED"
                    and isinstance(record.payload.get("advance"), Mapping)
                ),
                None,
            )
            return FundingScheduleResultV1(
                status="COMPLETE",
                reason="LEDGER_ALREADY_COVERS_DERIVED_WINDOW",
                observed_event_count=(
                    None
                    if prior_advance is None
                    else len(
                        prior_advance.payload["advance"].get(
                            "event_effective_ats", ()
                        )
                    )
                ),
                advance_id=(
                    None if prior_advance is None else prior_advance.event_id
                ),
                account_version=account.version,
            )
        coverage_end_at = coverage_end.isoformat()
        evidence = self._evidence(cycle_id)
        service = PaperTradingService(
            self._ledger,
            cost_models=(self._cost_model,),
            market_evidence=evidence,
            carry_evidence=evidence,
            require_execution_intent=True,
            max_position_notional=self._account_policy[
                "max_position_notional"
            ],
        )
        model = FundingSettlementModelV1(
            model_id="v332-okx-realized-funding-v1",
            model_version="v1",
            price_proxy_method=(
                "LAST_CONFIRMED_15M_CLOSE_NOT_AFTER_EFFECTIVE_AT"
            ),
            cost_model_id=self._cost_model.model_id,
            cost_model_digest=self._cost_model.model_digest,
            effective_from=self._cost_model.effective_from,
            effective_to=self._cost_model.effective_to,
        )
        return AdmittedSliceFundingScheduler(
            ledger=self._ledger, service=service
        ).run(
            account_id=account.account_id,
            coverage_end_at=coverage_end_at,
            data_slice=replay.data_slice,
            settlement_model=model,
        )

    def _observe_latest(
        self, *, cycle_id: str, granularity: str
    ) -> PaperAccountVersionV1:
        """Advance, or replay, one exact admitted QUOTE or MARK slice."""

        account = self._require_account()
        if granularity not in {"QUOTE", "MARK"}:
            raise V332PaperRuntimeError("V332_PAPER_OBSERVATION_KIND_INVALID")
        evidence = self._evidence(cycle_id)
        market = (
            evidence.latest_order_book_slice(HYPE_OKX_INSTRUMENT_ID)
            if granularity == "QUOTE"
            else evidence.latest_mark_slice(HYPE_OKX_INSTRUMENT_ID)
        )
        if market is None:
            raise V332PaperRuntimeError("V332_PAPER_OBSERVATION_NOT_ADMITTED")
        market_fact = {
            "symbol": market.symbol,
            "observed_at": market.observed_at,
            "available_at": market.available_at,
            "source_sha256": market.source_sha256,
            "market": market.to_dict(),
        }
        latest_market = next(
            (
                record
                for record in reversed(
                    self._ledger.load_records(account.account_id)
                )
                if record.event_type == "MARKET_OBSERVED"
            ),
            None,
        )
        if latest_market is not None and latest_market.payload == market_fact:
            # A prior public process may have committed this exact market fact
            # before an unknown funding failure.  Exact immutable equality is
            # recovery only while it remains the latest observed market; it
            # never permits replay behind a later distinct market fact.
            return account
        paper = PaperTradingService(
            self._ledger,
            cost_models=(self._cost_model,),
            market_evidence=evidence,
            carry_evidence=evidence,
            require_execution_intent=True,
            max_position_notional=self._account_policy[
                "max_position_notional"
            ],
        )
        return paper.observe(
            account_id=self.account_id,
            expected_account_version=account.version,
            market=market,
        )

    def status(self) -> Mapping[str, Any]:
        """Return a read-only operational view without creating missing facts."""

        records = self._ledger.load_records(self.account_id)
        account = None if not records else self._require_account().to_dict()
        projection = self._sessions.status(self.logical_agent_id)
        return {
            "schema_id": "agent-trade-emotion.v332-hype-paper-runtime-status",
            "schema_version": "1.0.0",
            "run_id": self._runtime.run_manifest.run_id,
            "experiment_policy_sha256": self._policy.policy_sha256,
            "setup_cycle_id": self._setup_cycle_id,
            "setup_slice_sealed_at": self._setup_slice.sealed_at,
            "external_orders_supported": False,
            "account": account,
            "agent_registry": (
                None
                if projection.registry is None
                else projection.registry.to_dict()
            ),
            "attention_request_ids": sorted(projection.requests),
            "ledger_revision": len(records),
            "ledger_head_record_sha256": (
                None if not records else records[-1].record_sha256
            ),
            "cost_model": self._cost_model.to_dict(),
            "cost_model_sha256": self._cost_model.model_digest,
        }


class V332AgentPaperActionPort:
    """Persistent-Goal transaction port for one direct local-paper action.

    The caller supplies only the sealed decision-cycle identity.  The physical
    Goal identity, account, action, prices, quantity, timestamps and mailbox
    paths are recovered from immutable registry, cycle, request and
    Agent-authored facts.  There is no paper-action worker, supervisor permit,
    dispatch ACK or attention prerequisite.  This port has no external-order
    transport and cannot elevate the experiment policy.
    """

    def __init__(self, paper_runtime: V332HypePaperRuntime) -> None:
        if not isinstance(paper_runtime, V332HypePaperRuntime):
            raise V332PaperRuntimeError("V332_PAPER_AGENT_PORT_INVALID")
        self._paper = paper_runtime

    @staticmethod
    def _cycle(value: str) -> str:
        if not isinstance(value, str) or not value:
            raise V332PaperRuntimeError("V332_PAPER_DECISION_CYCLE_INVALID")
        return value

    def prepare_paper_action(
        self, *, decision_cycle_id: str
    ) -> Mapping[str, Any]:
        """Issue the sole create-once intent request to the registered Goal."""

        with self._paper._runtime.mutation_guard():
            return self._prepare_paper_action(decision_cycle_id=decision_cycle_id)

    def _prepare_paper_action(
        self, *, decision_cycle_id: str
    ) -> Mapping[str, Any]:
        """Prepare while the direct Goal holds the lifecycle guard."""

        physical_goal_id = self._paper._require_current_goal_caller()
        cycle_id = self._cycle(decision_cycle_id)
        valid_until = self._paper._paper_action_hard_stop(cycle_id)
        issued = self._paper._issue_execution_intent_request(
            self._paper._intent_mailbox(),
            decision_cycle_id=cycle_id,
            valid_until=valid_until,
        )
        document = issued.document
        _, decision_goal_binding_sha256 = (
            self._paper._seal_decision_goal_binding(
                cycle_id,
                intent_request_sha256=issued.request_sha256,
                bound_at=str(document["issued_at"]),
            )
        )
        if document.get("physical_task_id") != physical_goal_id:
            raise V332PaperRuntimeError(
                "V332_PAPER_INTENT_REQUEST_GOAL_IDENTITY_MISMATCH"
            )
        return {
            "schema_id": "agent-trade-emotion.paper-action-preparation",
            "schema_version": "2.1.0",
            "status": "PREPARED",
            "run_id": self._paper._runtime.run_manifest.run_id,
            "cycle_id": cycle_id,
            "logical_agent_id": self._paper.logical_agent_id,
            "agent_generation": self._paper.agent_generation,
            "physical_goal_id": physical_goal_id,
            "intent_request_relative_path": (
                "transport/paper-execution-intent-request.json"
            ),
            "intent_request_sha256": issued.request_sha256,
            "decision_goal_binding_relative_path": (
                "transport/decision-goal-binding.json"
            ),
            "decision_goal_binding_sha256": decision_goal_binding_sha256,
            "issued_at": document["issued_at"],
            "valid_until": document["valid_until"],
        }

    def process_market_cycle(self, *, cycle_id: str) -> Mapping[str, Any]:
        """Apply one admitted cycle using the richest deterministic evidence.

        The persistent Goal chooses *when* to collect/process a cycle.  The
        mechanical paper tool chooses QUOTE when that admitted fact exists and
        otherwise MARK; callers cannot tune fill granularity or submit an
        action through this maintenance surface.
        """

        with self._paper._runtime.mutation_guard():
            return self._process_market_cycle(cycle_id=cycle_id)

    def _process_market_cycle(self, *, cycle_id: str) -> Mapping[str, Any]:
        """Process market facts while holding the run lifecycle guard."""

        physical_goal_id = self._paper._require_current_goal_caller()
        safe_cycle = self._cycle(cycle_id)
        evidence = self._paper._evidence(safe_cycle)
        granularity = (
            "QUOTE"
            if evidence.latest_order_book_slice(HYPE_OKX_INSTRUMENT_ID)
            is not None
            else "MARK"
        )
        self._paper._observe_latest(
            cycle_id=safe_cycle,
            granularity=granularity,
        )
        try:
            funding = self._paper._advance_funding(cycle_id=safe_cycle)
        except FundingSchedulerError as exc:
            reason = str(exc)
            if reason not in {
                "PAPER_FUNDING_WINDOW_NOT_FORWARD",
                "PAPER_FUNDING_MODEL_WINDOW_MISMATCH",
            }:
                # Identity, PIT, model-integrity and ledger errors remain hard
                # failures.  Exact market replay above makes their retry safe
                # after the underlying problem is corrected.
                raise
            partial_account = self._paper._require_account()
            funding = FundingScheduleResultV1(
                status="PARTIAL",
                reason=f"FUNDING_WINDOW_NOT_PROCESSABLE:{reason}",
                observed_event_count=None,
                advance_id=None,
                account_version=partial_account.version,
            )
        account = self._paper._require_account()
        runtime_status = self._paper.status()
        return {
            "schema_id": "agent-trade-emotion.paper-market-cycle-processing",
            "schema_version": "1.1.0",
            "status": "PROCESSED",
            "run_id": self._paper._runtime.run_manifest.run_id,
            "cycle_id": safe_cycle,
            "physical_goal_id": physical_goal_id,
            "observation_kind": granularity,
            "account_id": account.account_id,
            "ledger_after_revision": account.version,
            "ledger_after_head_record_sha256": runtime_status[
                "ledger_head_record_sha256"
            ],
            "funding": {
                "status": funding.status,
                "reason": funding.reason,
                "observed_event_count": funding.observed_event_count,
                "advance_id": funding.advance_id,
                "account_coverage_status": account.funding_coverage_status,
                "account_coverage_end_at": account.funding_coverage_end_at,
            },
        }

    @staticmethod
    def _validate_committed_ledger_suffix(
        *,
        before_records: tuple[Any, ...],
        suffix: tuple[Any, ...],
        intent: PaperExecutionIntentV1,
        received_at: str,
    ) -> None:
        """Prove the current head is exactly the prior intent transaction."""

        if (
            not suffix
            or suffix[0].revision != len(before_records) + 1
            or any(record.occurred_at != received_at for record in suffix)
            or canonical_bytes(suffix[0].payload.get("execution_intent"))
            != canonical_bytes(intent.to_dict())
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_ACTION_RECOVERY_LEDGER_DRIFT"
            )

        command = intent.command
        if command is None:
            expected_types = ("INTENT_RECORDED",)
            valid = tuple(record.event_type for record in suffix) == expected_types
        elif intent.bracket is not None:
            commands = intent.bracket.commands
            try:
                roots = []
                for record in before_records:
                    if record.event_type != "STATIC_NO_TRANSITION_PREREGISTERED":
                        continue
                    value = record.payload.get("comparator")
                    if not isinstance(value, Mapping):
                        raise PaperContractError(
                            "static comparator event payload mismatch"
                        )
                    candidate = StaticNoTransitionComparatorV1.from_dict(value)
                    root_intent = PaperExecutionIntentV1.from_dict(
                        candidate.execution_intent
                    )
                    if root_intent.episode_id == intent.episode_id:
                        roots.append(candidate)
                if len(roots) > 1:
                    raise PaperContractError(
                        "static comparator episode root is ambiguous"
                    )
                root = roots[0] if roots else None
                if root is None:
                    expected_types = (
                        "COMMAND_ACCEPTED",
                        "STATIC_NO_TRANSITION_PREREGISTERED",
                        "ORDER_OPENED",
                        *("ORDER_HELD" for _ in commands[1:]),
                    )
                    order_offset = 2
                    comparator_value = suffix[1].payload.get("comparator")
                    comparator = (
                        StaticNoTransitionComparatorV1.from_dict(
                            comparator_value
                        )
                        if isinstance(comparator_value, Mapping)
                        else None
                    )
                    comparator_valid = (
                        comparator is not None
                        and comparator.intent_sha256 == intent.intent_sha256
                        and canonical_bytes(comparator.execution_intent)
                        == canonical_bytes(intent.to_dict())
                        and "static_comparator_linkage"
                        not in suffix[0].payload
                    )
                else:
                    expected_types = (
                        "COMMAND_ACCEPTED",
                        "ORDER_OPENED",
                        *("ORDER_HELD" for _ in commands[1:]),
                    )
                    order_offset = 1
                    linkage_value = suffix[0].payload.get(
                        "static_comparator_linkage"
                    )
                    linkage = (
                        StaticNoTransitionEpisodeLinkV1.from_dict(
                            linkage_value
                        )
                        if isinstance(linkage_value, Mapping)
                        else None
                    )
                    prior_continuations = sum(
                        1
                        for record in before_records
                        if record.event_type
                        in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}
                        and isinstance(
                            record.payload.get("static_comparator_linkage"),
                            Mapping,
                        )
                        and record.payload["static_comparator_linkage"].get(
                            "root_comparator_id"
                        )
                        == root.comparator_id
                    )
                    comparator_valid = (
                        linkage is not None
                        and linkage.verifies(
                            root_comparator=root,
                            current_intent=intent,
                            continuation_index=prior_continuations + 1,
                        )
                    )
                order_ids = tuple(
                    record.payload.get("order", {}).get("order_id")
                    for record in suffix[order_offset:]
                )
                valid = (
                    tuple(record.event_type for record in suffix)
                    == expected_types
                    and comparator_valid
                    and order_ids
                    == tuple(item.command_id for item in commands)
                )
            except (IndexError, PaperContractError, TypeError, ValueError):
                valid = False
        elif command.command_type == "CANCEL":
            prior_account = replay_paper_account(before_records)
            prior_order_ids = {item.order_id for item in prior_account.orders}
            cancelled_ids = tuple(
                record.payload.get("order", {}).get("order_id")
                for record in suffix[1:]
            )
            valid = (
                len(suffix) >= 2
                and suffix[0].event_type == "COMMAND_ACCEPTED"
                and all(
                    record.event_type == "ORDER_CANCELLED"
                    for record in suffix[1:]
                )
                and cancelled_ids[0] == command.target_order_id
                and len(cancelled_ids) == len(set(cancelled_ids))
                and set(cancelled_ids).issubset(prior_order_ids)
            )
        else:
            order = (
                suffix[1].payload.get("order")
                if len(suffix) == 2
                else None
            )
            valid = (
                len(suffix) == 2
                and suffix[0].event_type == "COMMAND_ACCEPTED"
                and suffix[1].event_type
                in {"ORDER_OPENED", "ORDER_REJECTED"}
                and isinstance(order, Mapping)
                and order.get("order_id") == command.command_id
            )
        if not valid:
            raise V332PaperRuntimeError(
                "V332_PAPER_ACTION_RECOVERY_LEDGER_DRIFT"
            )

    @classmethod
    def _committed_transaction_end(
        cls,
        *,
        records: tuple[Any, ...],
        before_revision: int,
        intent: PaperExecutionIntentV1,
        received_at: str,
    ) -> int:
        """Find the shortest exact transaction prefix for receipt recovery.

        Later fills, funding or decisions may already follow an interrupted
        commit.  They are not part of this transaction and must not move its
        after-head.  Conversely, no malformed record may be silently swallowed
        into the recovered transaction.
        """

        before_records = records[:before_revision]
        for after_revision in range(before_revision + 1, len(records) + 1):
            try:
                cls._validate_committed_ledger_suffix(
                    before_records=before_records,
                    suffix=records[before_revision:after_revision],
                    intent=intent,
                    received_at=received_at,
                )
            except V332PaperRuntimeError:
                continue
            return after_revision
        raise V332PaperRuntimeError(
            "V332_PAPER_ACTION_RECOVERY_LEDGER_DRIFT"
        )

    def commit_paper_action(
        self, *, decision_cycle_id: str
    ) -> Mapping[str, Any]:
        """Commit one exact Goal-authored intent without supervisor approval."""

        with self._paper._runtime.mutation_guard():
            return self._commit_paper_action(decision_cycle_id=decision_cycle_id)

    def _commit_paper_action(
        self, *, decision_cycle_id: str
    ) -> Mapping[str, Any]:
        """Commit while the direct Goal holds the lifecycle guard."""

        physical_goal_id = self._paper._require_current_goal_caller()
        decision_cycle_id = self._cycle(decision_cycle_id)
        runtime = self._paper._runtime
        intent_mailbox = self._paper._intent_mailbox()
        transport = (
            runtime.runtime_root
            / "cycles"
            / decision_cycle_id
            / "transport"
        )
        request_path = intent_mailbox.intent_request_path(decision_cycle_id)
        receipt_path = transport / "paper-action-execution-receipt.json"
        request, request_raw = self._paper._read_canonical_document(
            request_path, code="V332_PAPER_AGENT_INTENT_NOT_RECEIVABLE"
        )
        request_sha256 = hashlib.sha256(request_raw).hexdigest()
        decision_goal_binding, decision_goal_binding_sha256 = (
            self._paper._load_decision_goal_binding(
                decision_cycle_id,
                intent_request_sha256=request_sha256,
            )
        )
        if (
            request.get("cycle_id") != decision_cycle_id
            or request.get("logical_agent_id") != self._paper.logical_agent_id
            or request.get("agent_generation") != self._paper.agent_generation
            or request.get("physical_task_id") != physical_goal_id
            or decision_goal_binding.get("physical_goal_id")
            != physical_goal_id
            or decision_goal_binding.get("decision_sha256")
            != request.get("decision_sha256")
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_INTENT_REQUEST_GOAL_IDENTITY_MISMATCH"
            )
        if not intent_mailbox.receipt_path(decision_cycle_id).exists():
            # A first receipt is a state change. Prove all immutable identity
            # bindings and the prospective window before allowing its write.
            # Recovery may proceed later only from an existing trusted receipt.
            self._paper._require_action_window(decision_cycle_id)
        try:
            received_intent = intent_mailbox.receive(decision_cycle_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise V332PaperRuntimeError(
                "V332_PAPER_AGENT_INTENT_NOT_RECEIVABLE"
            ) from exc

        intent = received_intent.intent
        if (
            intent.decision_cycle_id != decision_cycle_id
            or len(received_intent.intent_document_sha256) != 64
            or len(received_intent.receipt_sha256) != 64
            or hashlib.sha256(request_raw).hexdigest()
            != intent.execution_intent_request_sha256
        ):
            raise V332PaperRuntimeError("V332_PAPER_INTENT_RECEIPT_INVALID")
        records_current = self._paper._ledger.load_records(
            self._paper.account_id
        )
        if not records_current:
            raise V332PaperRuntimeError("V332_PAPER_LEDGER_HEAD_INVALID")
        before_revision = intent.expected_account_version
        if (
            before_revision < 1
            or before_revision > len(records_current)
            or records_current[before_revision - 1].record_sha256
            != intent.ledger_head_record_sha256
        ):
            raise V332PaperRuntimeError("V332_PAPER_LEDGER_HEAD_INVALID")
        matching_intent_facts = tuple(
            (offset, record)
            for offset, record in enumerate(
                records_current[before_revision:], start=before_revision
            )
            if record.event_type in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}
            and canonical_bytes(record.payload.get("execution_intent"))
            == canonical_bytes(intent.to_dict())
        )
        if len(matching_intent_facts) > 1:
            raise V332PaperRuntimeError(
                "V332_PAPER_EXECUTION_INTENT_CONFLICT"
            )
        existing_receipt: Mapping[str, Any] | None = None
        if receipt_path.exists():
            try:
                receipt_raw = receipt_path.read_bytes()
                existing_receipt = loads_json_strict(receipt_raw)
                if canonical_bytes(existing_receipt) + b"\n" != receipt_raw:
                    raise ValueError("execution receipt is not canonical")
                recorded_after_revision = existing_receipt.get(
                    "ledger_after_revision"
                )
                if (
                    type(recorded_after_revision) is not int
                    or recorded_after_revision <= before_revision
                    or recorded_after_revision > len(records_current)
                ):
                    raise ValueError("execution receipt revision is invalid")
            except (OSError, ValueError) as exc:
                raise V332PaperRuntimeError(
                    "V332_PAPER_ACTION_EXECUTION_RECEIPT_INVALID"
                ) from exc
        else:
            recorded_after_revision = None

        owner_facts_committed = bool(matching_intent_facts)
        if owner_facts_committed:
            if matching_intent_facts[0][0] != before_revision:
                raise V332PaperRuntimeError(
                    "V332_PAPER_EXECUTION_LEDGER_HEAD_STALE"
                )
            derived_after_revision = self._committed_transaction_end(
                records=tuple(records_current),
                before_revision=before_revision,
                intent=intent,
                received_at=received_intent.received_at,
            )
            after_revision = (
                int(recorded_after_revision)
                if recorded_after_revision is not None
                else derived_after_revision
            )
            if after_revision != derived_after_revision:
                raise V332PaperRuntimeError(
                    "V332_PAPER_ACTION_RECOVERY_LEDGER_DRIFT"
                )
            account_after = replay_paper_account(
                records_current[:after_revision]
            )
            records_after = records_current
        else:
            if len(records_current) != before_revision or existing_receipt:
                raise V332PaperRuntimeError(
                    "V332_PAPER_EXECUTION_LEDGER_HEAD_STALE"
                )
            self._paper._require_action_window(
                decision_cycle_id,
                received_at=received_intent.received_at,
            )
            # All rejection-capable policy/risk checks happen before the
            # ledger owner is mutated. The mailbox receipt is a transport fact,
            # not a supervisor permission.
            self._paper._validate_received_intent(
                intent,
                received_at=received_intent.received_at,
            )
            account_after = self._paper._submit_received_intent(
                intent,
                received_at=received_intent.received_at,
            )
            records_after = self._paper._ledger.load_records(
                self._paper.account_id
            )
            if (
                len(records_after) != account_after.version
                or account_after.version <= before_revision
            ):
                raise V332PaperRuntimeError(
                    "V332_PAPER_ACTION_FACT_OWNER_MISMATCH"
                )
            after_revision = account_after.version

        if (
            records_after[before_revision - 1].record_sha256
            != intent.ledger_head_record_sha256
            or records_after[after_revision - 1].revision != after_revision
        ):
            raise V332PaperRuntimeError(
                "V332_PAPER_ACTION_FACT_OWNER_MISMATCH"
            )
        receipt = {
            "schema_id": "agent-trade-emotion.paper-action-execution-receipt",
            "schema_version": "2.1.0",
            "status": "COMMITTED",
            "run_id": runtime.run_manifest.run_id,
            "cycle_id": decision_cycle_id,
            "logical_agent_id": self._paper.logical_agent_id,
            "agent_generation": self._paper.agent_generation,
            "physical_goal_id": physical_goal_id,
            "decision_sha256": intent.decision_sha256,
            "paper_context_sha256": intent.paper_context_sha256,
            "intent_sha256": intent.intent_sha256,
            "intent_request_sha256": intent.execution_intent_request_sha256,
            "decision_goal_binding_sha256": decision_goal_binding_sha256,
            "intent_document_sha256": received_intent.intent_document_sha256,
            "intent_receipt_sha256": received_intent.receipt_sha256,
            "account_id": self._paper.account_id,
            "ledger_before_revision": before_revision,
            "ledger_before_head_record_sha256": records_after[
                before_revision - 1
            ].record_sha256,
            "ledger_after_revision": after_revision,
            "ledger_after_head_record_sha256": records_after[
                after_revision - 1
            ].record_sha256,
            "completed_at": received_intent.received_at,
        }
        try:
            write_once_json(receipt_path, receipt)
            sealed_raw = receipt_path.read_bytes()
            sealed_receipt = loads_json_strict(sealed_raw)
            if (
                canonical_bytes(sealed_receipt) + b"\n" != sealed_raw
                or sealed_receipt != receipt
            ):
                raise ValueError("execution receipt does not match transaction")
        except (CanonicalContractError, OSError, ValueError) as exc:
            raise V332PaperRuntimeError(
                "V332_PAPER_ACTION_EXECUTION_RECEIPT_FAILED"
            ) from exc
        return sealed_receipt


__all__ = [
    "V332PaperRuntimeError",
]
