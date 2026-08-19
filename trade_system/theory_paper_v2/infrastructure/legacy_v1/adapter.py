"""Load committed V1 cycles without fabricating missing V2 state."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ...domain.contracts.canonical import canonical_digest
from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...application.ports import LegacySourcePort
from trade_system.theory_paper.common import digest_json, sha256_file, verify_ledger
from trade_system.theory_paper.experiment import _verify_latest_transaction_state
from trade_system.theory_paper.inference_v2.infrastructure import read_json_object


class LegacyAdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LegacyGapEntry:
    field_name: str
    status: str
    permitted_use: str
    reason: str


@dataclass(frozen=True, slots=True)
class LegacyCycleEnvelope:
    legacy_run_id: str
    cycle_id: str
    manifest_digest: str
    source_tree_digest_before: str
    source_tree_digest_after: str
    analysis_committed_at: str | None
    decision_committed_at: str | None
    market: Mapping[str, Any]
    market_execution: Mapping[str, Any]
    chaos_execution: Mapping[str, Any]
    news: Mapping[str, Any]
    analysis: Mapping[str, Any]
    agent_decision: Mapping[str, Any] | None
    validated_decision: Mapping[str, Any]
    source_artifact_digests: tuple[tuple[str, str], ...]
    gap_entries: tuple[LegacyGapEntry, ...]
    integrity_verdict: str
    usage_scope: str
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


def legacy_tree_digest(root: Path) -> str:
    """Digest every byte and relative path in a frozen legacy run tree."""

    resolved = Path(root).resolve(strict=True)
    hasher = hashlib.sha256()
    for path in sorted(
        item for item in resolved.rglob("*") if item.is_file()
    ):
        relative = path.relative_to(resolved).as_posix().encode("utf-8")
        payload = path.read_bytes()
        hasher.update(len(relative).to_bytes(8, "big"))
        hasher.update(relative)
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    return hasher.hexdigest()


def _artifact_digest(
    commit: Mapping[str, Any], relative_path: str, value: Mapping[str, Any]
) -> str:
    artifact_digests = commit.get("artifact_digests")
    if not isinstance(artifact_digests, Mapping):
        raise LegacyAdapterError("LEGACY_LEDGER_OR_TRANSACTION_INVALID")
    actual = digest_json(value)
    if artifact_digests.get(relative_path) != actual:
        raise LegacyAdapterError("LEGACY_MANIFEST_DIGEST_MISMATCH")
    return actual


class LegacyV1Adapter(LegacySourcePort):
    def __init__(
        self,
        *,
        expected_run_id: str,
        expected_source_tree_digest: str | None = None,
        full_chain_verifier: Callable[[Path], Mapping[str, Any]] | None = None,
    ) -> None:
        self.expected_run_id = expected_run_id
        self.expected_source_tree_digest = expected_source_tree_digest
        self.full_chain_verifier = (
            _verify_latest_transaction_state
            if full_chain_verifier is None
            else full_chain_verifier
        )

    def load_cycle(
        self, run_root: Path, cycle_id: int, expected_manifest_digest: str
    ) -> LegacyCycleEnvelope:
        if cycle_id < 1 or cycle_id > 24:
            raise LegacyAdapterError("LEGACY_CYCLE_OUT_OF_SCOPE")
        root = Path(run_root).resolve(strict=True)
        before = legacy_tree_digest(root)
        if (
            self.expected_source_tree_digest is not None
            and before != self.expected_source_tree_digest
        ):
            raise LegacyAdapterError("LEGACY_MANIFEST_DIGEST_MISMATCH")
        manifest_path = root / "manifest.json"
        manifest = read_json_object(manifest_path)
        manifest_digest = digest_json(manifest)
        if (
            manifest_digest != expected_manifest_digest
            or manifest.get("run_id") != self.expected_run_id
        ):
            raise LegacyAdapterError("LEGACY_MANIFEST_DIGEST_MISMATCH")
        boundary = manifest.get("authority_boundary")
        if not isinstance(boundary, Mapping) or (
            boundary.get("credential_capability") is not False
            or boundary.get("exchange_private_api_capability") is not False
            or boundary.get("live_order_capability") is not False
            or boundary.get("paper_permission") != "LOCAL_SIMULATION_ONLY"
        ):
            raise LegacyAdapterError("LEGACY_LEDGER_OR_TRANSACTION_INVALID")
        try:
            ledger = verify_ledger(root)
            transaction = self.full_chain_verifier(root)
        except Exception as exc:
            raise LegacyAdapterError("LEGACY_LEDGER_OR_TRANSACTION_INVALID") from exc
        if ledger.get("valid") is not True or transaction.get("valid") is not True:
            raise LegacyAdapterError("LEGACY_LEDGER_OR_TRANSACTION_INVALID")
        cycle_name = f"cycle-{cycle_id:04d}"
        cycle_root = root / "cycles" / cycle_name
        market = read_json_object(cycle_root / "market.json")
        market_execution = read_json_object(
            cycle_root / "market-execution.json"
        )
        chaos_execution = read_json_object(
            cycle_root / "chaos-execution.json"
        )
        news = read_json_object(cycle_root / "news.json")
        analysis = read_json_object(cycle_root / "analysis.json")
        decision = read_json_object(cycle_root / "decision.json")
        analysis_commit_path = (
            root / "transactions" / f"{cycle_name}-analysis.commit.json"
        )
        decision_commit_path = (
            root / "transactions" / f"{cycle_name}-decision.commit.json"
        )
        analysis_commit = read_json_object(analysis_commit_path)
        decision_commit = read_json_object(decision_commit_path)
        if (
            analysis_commit.get("transaction_id") != f"{cycle_name}-analysis"
            or analysis_commit.get("ledger_event_type") != "HOURLY_ANALYSIS_FROZEN"
            or decision_commit.get("transaction_id") != f"{cycle_name}-decision"
            or decision_commit.get("ledger_event_type") != "AGENT_DECISION_APPLIED"
        ):
            raise LegacyAdapterError("LEGACY_LEDGER_OR_TRANSACTION_INVALID")
        digests = {
            "manifest.json.physical_sha256": sha256_file(manifest_path),
            "ledger.ndjson.physical_sha256": sha256_file(root / "ledger.ndjson"),
            "analysis.commit.json.physical_sha256": sha256_file(
                analysis_commit_path
            ),
            "decision.commit.json.physical_sha256": sha256_file(
                decision_commit_path
            ),
            "market.json": _artifact_digest(
                analysis_commit, f"cycles/{cycle_name}/market.json", market
            ),
            "market-execution.json": _artifact_digest(
                analysis_commit,
                f"cycles/{cycle_name}/market-execution.json",
                market_execution,
            ),
            "chaos-execution.json": _artifact_digest(
                analysis_commit,
                f"cycles/{cycle_name}/chaos-execution.json",
                chaos_execution,
            ),
            "news.json": _artifact_digest(
                analysis_commit, f"cycles/{cycle_name}/news.json", news
            ),
            "analysis.json": _artifact_digest(
                analysis_commit, f"cycles/{cycle_name}/analysis.json", analysis
            ),
            "decision.json": _artifact_digest(
                decision_commit, f"cycles/{cycle_name}/decision.json", decision
            ),
        }
        validated = decision.get("validated_decision")
        if not isinstance(validated, Mapping):
            raise LegacyAdapterError("LEGACY_FIELD_MAPPING_AMBIGUOUS")
        if (
            decision.get("analysis_digest") != digests["analysis.json"]
            or decision.get("cycle_id") != cycle_name
        ):
            raise LegacyAdapterError("LEGACY_FIELD_MAPPING_AMBIGUOUS")
        agent_path = cycle_root / "agent-decision.json"
        gaps: list[LegacyGapEntry] = []
        if agent_path.is_file():
            agent_decision: Mapping[str, Any] | None = read_json_object(agent_path)
            digests["agent-decision.json.physical_sha256"] = sha256_file(agent_path)
            if (
                agent_decision.get("analysis_digest") != analysis.get("analysis_digest")
                or validated.get("analysis_digest") != analysis.get("analysis_digest")
                or agent_decision.get("decision_at") != analysis.get("decision_at")
                or validated.get("decision_at") != analysis.get("decision_at")
            ):
                raise LegacyAdapterError("LEGACY_FIELD_MAPPING_AMBIGUOUS")
        else:
            agent_decision = None
            gaps.append(
                LegacyGapEntry(
                    field_name="agent_decision",
                    status="UNKNOWN_LEGACY_UNDECLARED",
                    permitted_use="EVALUATION_ONLY",
                    reason="committed validated decision exists but raw Agent artifact is absent",
                )
            )
        for field_name in (
            "strategic_episode_state",
            "core_tactical_lot_role",
            "reentry_contract",
            "geometry_lifecycle",
        ):
            gaps.append(
                LegacyGapEntry(
                    field_name=field_name,
                    status="UNKNOWN_LEGACY_UNDECLARED",
                    permitted_use="NONE",
                    reason="V1 did not declare this V2 authoritative object",
                )
            )
        after = legacy_tree_digest(root)
        if after != before:
            raise LegacyAdapterError("LEGACY_WRITE_ATTEMPT_FORBIDDEN")
        envelope = LegacyCycleEnvelope(
            legacy_run_id=self.expected_run_id,
            cycle_id=cycle_name,
            manifest_digest=manifest_digest,
            source_tree_digest_before=before,
            source_tree_digest_after=after,
            analysis_committed_at=analysis_commit.get("committed_at"),
            decision_committed_at=decision.get("decided_at"),
            market=market,
            market_execution=market_execution,
            chaos_execution=chaos_execution,
            news=news,
            analysis=analysis,
            agent_decision=agent_decision,
            validated_decision=validated,
            source_artifact_digests=tuple(sorted(digests.items())),
            gap_entries=tuple(gaps),
            integrity_verdict="PASS",
            usage_scope="HISTORICAL_COUNTERFACTUAL_REPLAY",
        )
        # Force a deterministic serialization check without persisting it.
        canonical_digest(
            {
                "legacy_run_id": envelope.legacy_run_id,
                "cycle_id": envelope.cycle_id,
                "manifest_digest": envelope.manifest_digest,
                "gap_entries": [
                    {
                        "field_name": item.field_name,
                        "status": item.status,
                        "permitted_use": item.permitted_use,
                        "reason": item.reason,
                    }
                    for item in envelope.gap_entries
                ],
            }
        )
        return envelope
