"""Rebuildable workbench projection over data, Goal-checkpoint, and paper owners.

The checkpoint projection exposes only the Agent registry and its latest
Agent-authored next-check request.  There is no approval, wake receipt,
dispatch, or wake-packet projection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol, Sequence

from ...application.market_cycle.attention import AttentionService
from ...application.market_cycle.paper import replay_paper_account
from ...application.market_cycle.paper_valuation import project_paper_valuation
from ...application.market_cycle.read_models import (
    WorkbenchSnapshotV1,
    project_agent_state,
    project_data_coverage,
    project_fact_timeline,
    project_orders_and_fills,
    project_paper_account,
    project_paper_cost_effect,
    project_portfolio,
)
from ...domain.market_cycle.data import AssetDataSliceV1
from ...domain.market_cycle.paper import PaperMarketSliceV1
from .attention_repository import FileAttentionRepository
from .paper_ledger import FilePaperLedger
from .repository import FileCycleRepository


class WorkbenchProjectionError(RuntimeError):
    """A requested fact owner cannot be projected into the workbench."""


class PaperValuationMarketEvidencePort(Protocol):
    """Read already-admitted paper slices without owning or rewriting raw data."""

    def derive_slices(self, symbol: str) -> tuple[PaperMarketSliceV1, ...]: ...


class WorkbenchProjectionService:
    """Read owner facts and create a disposable six-view snapshot."""

    def __init__(
        self,
        *,
        attention_repository: FileAttentionRepository,
        paper_ledger: FilePaperLedger,
        cycle_repository: FileCycleRepository | None = None,
        valuation_market_evidence: PaperValuationMarketEvidencePort | None = None,
    ) -> None:
        self._attention_repository = attention_repository
        self._paper_ledger = paper_ledger
        self._cycle_repository = cycle_repository
        self._valuation_market_evidence = valuation_market_evidence

    def build(
        self,
        *,
        logical_agent_ids: Sequence[str],
        account_ids: Sequence[str],
        data_slices: Sequence[AssetDataSliceV1] = (),
        cycle_ids: Sequence[str] = (),
    ) -> WorkbenchSnapshotV1:
        if len(set(logical_agent_ids)) != len(logical_agent_ids):
            raise WorkbenchProjectionError("WORKBENCH_AGENT_ID_DUPLICATE")
        if len(set(account_ids)) != len(account_ids):
            raise WorkbenchProjectionError("WORKBENCH_ACCOUNT_ID_DUPLICATE")
        if len(set(cycle_ids)) != len(cycle_ids):
            raise WorkbenchProjectionError("WORKBENCH_CYCLE_ID_DUPLICATE")
        if cycle_ids and self._cycle_repository is None:
            raise WorkbenchProjectionError("WORKBENCH_CYCLE_REPOSITORY_REQUIRED")
        checkpoint_service = AttentionService(self._attention_repository)
        checkpoint_projections = tuple(
            checkpoint_service.status(logical_agent_id)
            for logical_agent_id in logical_agent_ids
        )
        paper_records = tuple(
            self._paper_ledger.load_records(account_id) for account_id in account_ids
        )
        accounts = tuple(replay_paper_account(records) for records in paper_records)
        account_histories = tuple(
            tuple(
                replay_paper_account(records[:revision])
                for revision in range(1, len(records) + 1)
            )
            for records in paper_records
        )
        market_slices_by_account: dict[str, list[PaperMarketSliceV1]] = {
            account_id: [] for account_id in account_ids
        }
        admitted_market_slices_by_symbol: dict[str, list[PaperMarketSliceV1]] = {}
        for account_id, records in zip(account_ids, paper_records):
            for record in records:
                if record.event_type != "MARKET_OBSERVED":
                    continue
                market_payload = record.payload.get("market")
                if not isinstance(market_payload, Mapping):
                    continue
                market = PaperMarketSliceV1(**dict(market_payload))
                market_slices_by_account[account_id].append(market)
        admitted_marks: dict[
            tuple[str, str, str, str, str], AssetDataSliceV1
        ] = {}
        for data_slice in data_slices:
            mark = data_slice.core_observations.get("mark_price")
            if not isinstance(mark, Mapping):
                raise WorkbenchProjectionError("WORKBENCH_ADMITTED_MARK_INVALID")
            raw_available_at = mark.get("available_at")
            if not isinstance(raw_available_at, str) or not raw_available_at:
                raise WorkbenchProjectionError("WORKBENCH_ADMITTED_MARK_INVALID")
            evidence_available_at = max(
                (raw_available_at, data_slice.sealed_at),
                key=lambda value: datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                ),
            )
            values = (
                data_slice.instrument_identity.venue_symbol,
                mark.get("value"),
                mark.get("observed_at"),
                evidence_available_at,
                mark.get("raw_sha256"),
            )
            if not all(isinstance(item, str) and item for item in values):
                raise WorkbenchProjectionError("WORKBENCH_ADMITTED_MARK_INVALID")
            admitted_marks[values] = data_slice
        if self._valuation_market_evidence is not None:
            for symbol in sorted({item[0] for item in admitted_marks}):
                derived = self._valuation_market_evidence.derive_slices(symbol)
                matched = 0
                for market in derived:
                    key = (
                        market.symbol,
                        market.mark,
                        market.observed_at,
                        market.available_at,
                        market.source_sha256,
                    )
                    if market.granularity == "MARK" and key in admitted_marks:
                        admitted_market_slices_by_symbol.setdefault(symbol, []).append(
                            market
                        )
                        matched += 1
                expected = sum(1 for item in admitted_marks if item[0] == symbol)
                if matched != expected:
                    raise WorkbenchProjectionError(
                        "WORKBENCH_ADMITTED_MARK_EVIDENCE_MISMATCH"
                    )
        valuations = tuple(
            project_paper_valuation(
                account,
                tuple(market_slices_by_account.get(account.account_id, ()))
                + tuple(
                    admitted_market_slices_by_symbol.get(
                        account.permitted_symbol, ()
                    )
                ),
                account_history=account_history,
            )
            for account, account_history in zip(accounts, account_histories)
        )
        cost_effects = tuple(
            project_paper_cost_effect(account, records)
            for account, records in zip(accounts, paper_records)
        )
        cycle_artifacts: list[dict[str, object]] = []
        if self._cycle_repository is not None:
            for cycle_id in cycle_ids:
                state = self._cycle_repository.load_state(cycle_id)
                for revision, reference in enumerate(state.artifact_refs, start=1):
                    artifact = self._cycle_repository.load_artifact(
                        cycle_id, reference.artifact_type
                    )
                    sealed_at = artifact.get("sealed_at")
                    if not isinstance(sealed_at, str):
                        raise WorkbenchProjectionError(
                            "WORKBENCH_CYCLE_ARTIFACT_TIME_INVALID"
                        )
                    cycle_artifacts.append(
                        {
                            "cycle_id": cycle_id,
                            "revision": revision,
                            "sealed_at": sealed_at,
                            "artifact_ref": reference.to_dict(),
                        }
                    )
        return WorkbenchSnapshotV1(
            data_coverage=tuple(project_data_coverage(item) for item in data_slices),
            agent_states=tuple(
                project_agent_state(item) for item in checkpoint_projections
            ),
            paper_accounts=tuple(
                project_paper_account(account, valuation, cost_effect)
                for account, valuation, cost_effect in zip(
                    accounts, valuations, cost_effects
                )
            ),
            orders_and_fills=tuple(
                project_orders_and_fills(account, records)
                for account, records in zip(accounts, paper_records)
            ),
            timeline=project_fact_timeline(
                tuple(
                    event
                    for logical_agent_id in logical_agent_ids
                    for event in self._attention_repository.replay(logical_agent_id)
                ),
                tuple(record for records in paper_records for record in records),
                tuple(cycle_artifacts),
            ),
            portfolio=project_portfolio(accounts, valuations, cost_effects),
        )
