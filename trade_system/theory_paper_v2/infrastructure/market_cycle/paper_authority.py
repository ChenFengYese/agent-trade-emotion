"""Read-only paper authority bound to durable Agent and cycle facts.

This adapter does not authorize an action by interpreting Agent prose.  It
only proves that the supplied decision digest belongs to the exact decision
cycle named by the command and already sealed by the existing market-cycle
repository for the current logical-Agent generation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import stat
from types import MappingProxyType
from typing import Mapping, Sequence

from ...application.market_cycle.agent_session import AgentSessionService
from ...application.market_cycle.attention import AttentionApplicationError
from ...domain.contracts.canonical import canonical_bytes, loads_json_strict
from ...domain.market_cycle.paper import PaperCommandV1, PaperExecutionIntentV1
from .repository import FileCycleRepository, MarketCycleRepositoryError


class PaperDecisionAuthorityConfigurationError(ValueError):
    """The adapter was not given a finite, explicit Agent-to-cycle scope."""


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bindings(
    value: Mapping[str, Sequence[str]],
) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(value, Mapping) or not value:
        raise PaperDecisionAuthorityConfigurationError(
            "PAPER_DECISION_AGENT_CYCLE_BINDINGS_REQUIRED"
        )
    result: dict[str, tuple[str, ...]] = {}
    for logical_agent_id, cycle_ids in value.items():
        cycles = tuple(cycle_ids)
        if (
            not isinstance(logical_agent_id, str)
            or not logical_agent_id
            or not cycles
            or len(cycles) != len(set(cycles))
            or any(not isinstance(item, str) or not item for item in cycles)
        ):
            raise PaperDecisionAuthorityConfigurationError(
                "PAPER_DECISION_AGENT_CYCLE_BINDING_INVALID"
            )
        result[logical_agent_id] = cycles
    return MappingProxyType(result)


class SealedCyclePaperDecisionAuthority:
    """Implement ``PaperDecisionAuthorityPort`` from existing durable facts.

    A command is accepted only when the durable bindings agree:

    * ``AgentSessionService.current`` reports the command generation;
    * the caller-supplied finite scope admits the exact decision cycle; and
    * the cycle repository exposes a sealed HypothesisRecord (and, when
      present, the derived BehaviorPlan) carrying the exact digest before the
      command submission time.

    The post-decision execution-intent request separately binds the current
    persistent Goal's physical identity, the immutable decision request,
    paper context and ledger head.  Attention/checkpoint state is deliberately
    outside this authority: failing to write a next-check preference cannot
    deny an otherwise legal local-paper action.

    The repository remains the sole owner of decision artifacts.  This class
    holds no index, cache, or second copy of them.
    """

    def __init__(
        self,
        *,
        sessions: AgentSessionService,
        cycle_repository: FileCycleRepository,
        agent_cycle_bindings: Mapping[str, Sequence[str]],
    ) -> None:
        if not isinstance(sessions, AgentSessionService):
            raise PaperDecisionAuthorityConfigurationError(
                "PAPER_DECISION_AGENT_SESSION_SERVICE_INVALID"
            )
        if not isinstance(cycle_repository, FileCycleRepository):
            raise PaperDecisionAuthorityConfigurationError(
                "PAPER_DECISION_CYCLE_REPOSITORY_INVALID"
            )
        self._sessions = sessions
        self._cycles = cycle_repository
        self._bindings = _bindings(agent_cycle_bindings)

    def current_generation(self, logical_agent_id: str) -> int | None:
        try:
            return self._sessions.current(logical_agent_id).generation
        except AttentionApplicationError as exc:
            if str(exc) == "ATTENTION_AGENT_NOT_REGISTERED":
                return None
            raise

    def verifies_decision(self, command: PaperCommandV1) -> bool:
        if not isinstance(command, PaperCommandV1):
            return False
        admitted_cycles = self._bindings.get(command.logical_agent_id)
        if (
            admitted_cycles is None
            or command.decision_cycle_id not in admitted_cycles
        ):
            return False
        try:
            registry = self._sessions.current(command.logical_agent_id)
        except AttentionApplicationError:
            return False
        if (
            registry.generation != command.agent_generation
            or registry.symbol != command.symbol
        ):
            return False

        return self._cycle_verifies(
            command,
            cycle_id=command.decision_cycle_id,
        )

    def verifies_execution_intent(
        self, execution_intent: PaperExecutionIntentV1
    ) -> bool:
        """Bind the exact intent to the exact decision request and paper head."""

        if not isinstance(execution_intent, PaperExecutionIntentV1):
            return False
        commands = (
            ()
            if execution_intent.command is None
            else (
                execution_intent.bracket.commands
                if execution_intent.bracket is not None
                else (execution_intent.command,)
            )
        )
        if (
            not self._verifies_intent_decision(execution_intent)
            or any(
                command.account_id != execution_intent.account_id
                or command.logical_agent_id != execution_intent.logical_agent_id
                or command.agent_generation != execution_intent.agent_generation
                or command.decision_cycle_id
                != execution_intent.decision_cycle_id
                or command.decision_sha256 != execution_intent.decision_sha256
                or command.expected_account_version
                != execution_intent.expected_account_version
                or command.symbol != execution_intent.symbol
                or command.submitted_at != execution_intent.authored_at
                for command in commands
            )
            or any(not self.verifies_decision(command) for command in commands)
        ):
            return False
        try:
            registry = self._sessions.current(execution_intent.logical_agent_id)
        except AttentionApplicationError:
            return False
        path = (
            self._cycles.root
            / execution_intent.decision_cycle_id
            / "transport"
            / "agent-request.json"
        )
        intent_request_path = (
            self._cycles.root
            / execution_intent.decision_cycle_id
            / "transport"
            / "paper-execution-intent-request.json"
        )
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                return False
            raw = path.read_bytes()
            request = loads_json_strict(raw)
            if canonical_bytes(request) + b"\n" != raw:
                return False
            intent_request_metadata = intent_request_path.lstat()
            if (
                stat.S_ISLNK(intent_request_metadata.st_mode)
                or not stat.S_ISREG(intent_request_metadata.st_mode)
            ):
                return False
            intent_request_raw = intent_request_path.read_bytes()
            intent_request = loads_json_strict(intent_request_raw)
            if canonical_bytes(intent_request) + b"\n" != intent_request_raw:
                return False
        except (OSError, ValueError):
            return False
        packet = request.get("packet")
        paper_context = (
            packet.get("paper_context") if isinstance(packet, Mapping) else None
        )
        head = (
            paper_context.get("ledger_head")
            if isinstance(paper_context, Mapping)
            else None
        )
        policy = (
            paper_context.get("paper_account_policy")
            if isinstance(paper_context, Mapping)
            else None
        )
        account = (
            paper_context.get("account")
            if isinstance(paper_context, Mapping)
            else None
        )
        valuation = (
            paper_context.get("valuation")
            if isinstance(paper_context, Mapping)
            else None
        )
        try:
            positions = account["positions"]
            current_quantity = Decimal("0")
            for position in positions:
                if position.get("symbol") == execution_intent.symbol:
                    current_quantity = Decimal(position["quantity"])
            pre_quantity = Decimal(
                str(execution_intent.pre_state["signed_quantity"])
            )
            target_quantity = Decimal(
                str(execution_intent.target_state["signed_quantity"])
            )
            maximum_loss = Decimal(
                str(execution_intent.risk_budget["maximum_loss"])
            )
            declared_notional_cap = Decimal(
                str(execution_intent.risk_budget["notional_cap"])
            )
            declared_drawdown_cap = Decimal(
                str(execution_intent.risk_budget["max_observed_drawdown"])
            )
            policy_loss_cap = Decimal(str(policy["max_decision_loss"]))
            policy_notional_cap = Decimal(str(policy["max_position_notional"]))
            policy_drawdown_cap = Decimal(str(policy["max_observed_drawdown"]))
            multiplier = Decimal(str(account["instrument_spec"]["contract_multiplier"]))
            reference_mark = Decimal(str(valuation["mark"]))
            target_notional = abs(target_quantity) * multiplier * reference_mark
            observed_drawdown = valuation.get("observed_max_drawdown")
            drawdown_amount = (
                None
                if observed_drawdown is None
                else Decimal(str(account["initial_balance"]))
                * Decimal(str(observed_drawdown))
            )
            cost_model_id = str(policy["cost_model"]["model_id"])
            cost_effective_from = policy["cost_model"].get("effective_from")
            cost_effective_to = policy["cost_model"].get("effective_to")
            request_issued_at = _moment(str(intent_request["issued_at"]))
            request_valid_until = _moment(str(intent_request["valid_until"]))
        except (
            InvalidOperation,
            KeyError,
            TypeError,
            ValueError,
        ):
            return False
        return bool(
            intent_request.get("schema_id")
            == "agent-trade-emotion.paper-execution-intent-request"
            and intent_request.get("schema_version") == "1.0.0"
            and hashlib.sha256(intent_request_raw).hexdigest()
            == execution_intent.execution_intent_request_sha256
            and intent_request.get("cycle_id")
            == execution_intent.decision_cycle_id
            and intent_request.get("logical_agent_id")
            == execution_intent.logical_agent_id
            and intent_request.get("agent_generation")
            == execution_intent.agent_generation
            and intent_request.get("physical_task_id")
            == registry.physical_task_id
            and intent_request.get("decision_sha256")
            == execution_intent.decision_sha256
            and intent_request.get("account_id") == execution_intent.account_id
            and intent_request.get("symbol") == execution_intent.symbol
            and intent_request.get("expected_account_version")
            == execution_intent.expected_account_version
            and intent_request.get("decision_request_sha256")
            == execution_intent.decision_request_sha256
            and intent_request.get("paper_context_sha256")
            == execution_intent.paper_context_sha256
            and intent_request.get("ledger_head_record_sha256")
            == execution_intent.ledger_head_record_sha256
            and intent_request.get("agent_request_document_sha256")
            == hashlib.sha256(raw).hexdigest()
            and execution_intent.action
            in intent_request.get("allowed_actions", ())
            and request_issued_at <= _moment(execution_intent.authored_at)
            and _moment(execution_intent.valid_until) <= request_valid_until
            and request.get("packet_sha256")
            == execution_intent.decision_request_sha256
            and isinstance(packet, Mapping)
            and packet.get("cycle_id") == execution_intent.decision_cycle_id
            and isinstance(paper_context, Mapping)
            and paper_context.get("paper_context_sha256")
            == execution_intent.paper_context_sha256
            and isinstance(head, Mapping)
            and head.get("revision")
            == execution_intent.expected_account_version
            and head.get("record_sha256")
            == execution_intent.ledger_head_record_sha256
            and account.get("account_id") == execution_intent.account_id
            and account.get("version")
            == execution_intent.expected_account_version
            and account.get("owner_logical_agent_id")
            == execution_intent.logical_agent_id
            and account.get("owner_agent_generation")
            == execution_intent.agent_generation
            and account.get("permitted_symbol") == execution_intent.symbol
            and all(command.cost_model_id == cost_model_id for command in commands)
            and (
                cost_effective_from is None
                or _moment(str(cost_effective_from))
                <= _moment(execution_intent.authored_at)
            )
            and (
                cost_effective_to is None
                or _moment(execution_intent.authored_at)
                < _moment(str(cost_effective_to))
            )
            and pre_quantity == current_quantity
            and maximum_loss <= policy_loss_cap
            and declared_notional_cap <= policy_notional_cap
            and declared_drawdown_cap <= policy_drawdown_cap
            and target_notional <= policy_notional_cap
            and (drawdown_amount is None or drawdown_amount <= policy_drawdown_cap)
            and hashlib.sha256(canonical_bytes(packet)).hexdigest()
            == execution_intent.decision_request_sha256
        )

    def _verifies_intent_decision(
        self, execution_intent: PaperExecutionIntentV1
    ) -> bool:
        admitted_cycles = self._bindings.get(execution_intent.logical_agent_id)
        if (
            admitted_cycles is None
            or execution_intent.decision_cycle_id not in admitted_cycles
        ):
            return False
        try:
            registry = self._sessions.current(execution_intent.logical_agent_id)
            record = self._cycles.load_artifact(
                execution_intent.decision_cycle_id, "HypothesisRecord"
            )
            plan = self._cycles.load_artifact(
                execution_intent.decision_cycle_id, "BehaviorPlan"
            )
        except (AttentionApplicationError, MarketCycleRepositoryError):
            return False
        authored_at = _moment(execution_intent.authored_at)
        return bool(
            registry.generation == execution_intent.agent_generation
            and registry.symbol == execution_intent.symbol
            and record.get("cycle_id") == execution_intent.decision_cycle_id
            and record.get("agent_decision_sha256")
            == execution_intent.decision_sha256
            and isinstance(record.get("sealed_at"), str)
            and _moment(record["sealed_at"]) <= authored_at
            and plan.get("cycle_id") == execution_intent.decision_cycle_id
            and plan.get("agent_decision_sha256")
            == execution_intent.decision_sha256
            and isinstance(plan.get("sealed_at"), str)
            and _moment(plan["sealed_at"]) <= authored_at
        )

    def _cycle_verifies(self, command: PaperCommandV1, *, cycle_id: str) -> bool:
        try:
            cycle_request = self._cycles.load_request(cycle_id)
            if cycle_request.instrument_id != command.symbol:
                return False
            record = self._cycles.load_artifact(cycle_id, "HypothesisRecord")
        except MarketCycleRepositoryError:
            return False
        if (
            record.get("cycle_id") != cycle_id
            or record.get("agent_decision_sha256") != command.decision_sha256
            or not isinstance(record.get("sealed_at"), str)
            or _moment(record["sealed_at"]) > _moment(command.submitted_at)
        ):
            return False

        # Execution is only eligible after the full Agent-owned BehaviorPlan is
        # sealed.  A HypothesisRecord alone proves authorship, not the complete
        # entry/exit/risk plan required by the paper boundary.
        try:
            plan = self._cycles.load_artifact(cycle_id, "BehaviorPlan")
        except MarketCycleRepositoryError as exc:
            if str(exc) == "MARKET_CYCLE_ARTIFACT_NOT_REFERENCED":
                return False
            return False
        return bool(
            plan.get("cycle_id") == cycle_id
            and plan.get("agent_decision_sha256") == command.decision_sha256
            and isinstance(plan.get("sealed_at"), str)
            and _moment(plan["sealed_at"]) <= _moment(command.submitted_at)
        )


__all__ = [
    "PaperDecisionAuthorityConfigurationError",
    "SealedCyclePaperDecisionAuthority",
]
