"""Immutable freeze and offline verification for official public market data."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from .binance_usdm import (
    BINANCE_USDM_BASE_URL,
    FORMAL_REQUESTED_CLOSED_BAR_COUNT,
    BinanceUsdmFreshCollector,
)
from .model import (
    CollectedPublicResponses,
    PublicRequestCapture,
    QualityStatus,
    require_digest,
    require_id,
)
from .quality import (
    FORMAL_CLOSED_BAR_COUNT,
    FORMAL_DECISION_INDEX_END,
    FORMAL_DECISION_INDEX_START,
    FORMAL_EXPERIMENT_CONTRACT_DIGEST,
    FORMAL_OUTCOME_HORIZONS,
    PreparedFreshMarketDataset,
    prepare_fresh_market_dataset,
)
from .store import FreshMarketWriteOnceStore


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_EXPERIMENT_CONTRACT = (
    _PROJECT_ROOT
    / "config"
    / "theory_agent_v2.formal_e0_experiment.v1.json"
)


class FreshMarketFreezeError(ValueError):
    """A bundle could not be frozen or verified without ambiguity."""


@dataclass(frozen=True, slots=True)
class FreshMarketFreezeResult:
    bundle_id: str
    bundle_root: Path
    manifest_path: Path
    manifest_digest: str
    quality_status: QualityStatus
    closed_bar_count: int
    decision_slot_count: int
    replay_admissibility_status: QualityStatus


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FreshMarketFreezeError("CLOCK_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FreshMarketFreezeError("CLOCK_TIME_INVALID") from exc
    return parsed


def _parse_pairs(
    value: object, *, key_name: str, value_name: str
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {key_name, value_name}
            or not isinstance(item[key_name], str)
            or not isinstance(item[value_name], str)
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        pairs.append((item[key_name], item[value_name]))
    return tuple(pairs)


def _capture_from_dict(value: Mapping[str, object]) -> PublicRequestCapture:
    expected = {
        "request_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "response_received_at",
        "final_url",
        "http_status",
        "selected_response_headers",
        "response_headers_digest",
        "raw_body_sha256",
        "raw_body_byte_length",
        "request_identity_digest",
        "record_digest",
    }
    if set(value) != expected:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    string_fields = (
        "request_id",
        "method",
        "base_url",
        "path",
        "final_url",
        "response_headers_digest",
        "raw_body_sha256",
        "request_identity_digest",
        "record_digest",
    )
    if any(not isinstance(value[field], str) for field in string_fields):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    if (
        not isinstance(value["http_status"], int)
        or isinstance(value["http_status"], bool)
        or not isinstance(value["raw_body_byte_length"], int)
        or isinstance(value["raw_body_byte_length"], bool)
    ):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    return PublicRequestCapture(
        request_id=str(value["request_id"]),
        method=str(value["method"]),
        base_url=str(value["base_url"]),
        path=str(value["path"]),
        query=_parse_pairs(
            value["query"], key_name="name", value_name="value"
        ),
        request_started_at=_parse_timestamp(
            value["request_started_at"]
        ),
        response_received_at=_parse_timestamp(
            value["response_received_at"]
        ),
        final_url=str(value["final_url"]),
        http_status=int(value["http_status"]),
        selected_response_headers=_parse_pairs(
            value["selected_response_headers"],
            key_name="name",
            value_name="value",
        ),
        response_headers_digest=str(
            value["response_headers_digest"]
        ),
        raw_body_sha256=str(value["raw_body_sha256"]),
        raw_body_byte_length=int(value["raw_body_byte_length"]),
        request_identity_digest=str(
            value["request_identity_digest"]
        ),
        record_digest=str(value["record_digest"]),
    )


def _load_and_validate_experiment_contract(path: Path) -> tuple[dict[str, object], bytes]:
    raw = Path(path).read_bytes()
    contract = load_json_strict(Path(path))
    try:
        digest = verify_self_digest(contract, "contract_digest")
    except ValueError as exc:
        raise FreshMarketFreezeError(
            "EVIDENCE_LINEAGE_INVALID"
        ) from exc
    if digest != FORMAL_EXPERIMENT_CONTRACT_DIGEST:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    data = contract.get("data_contract")
    sample = contract.get("sample_contract")
    if (
        contract.get("system_mode") != SYSTEM_MODE
        or contract.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or not isinstance(data, dict)
        or data.get("server_time_endpoint")
        != f"{BINANCE_USDM_BASE_URL}/fapi/v1/time"
        or data.get("kline_endpoint")
        != f"{BINANCE_USDM_BASE_URL}/fapi/v1/klines"
        or data.get("requested_closed_bar_count")
        != FORMAL_CLOSED_BAR_COUNT
        or data.get("end_time_rule")
        != "FLOOR_OFFICIAL_SERVER_TIME_TO_HOUR_MINUS_1_MILLISECOND"
        or data.get("open_bar_disposition") != "EXCLUDE"
        or not isinstance(sample, dict)
        or sample.get("warmup_bar_count") != 96
        or sample.get("topology_selection_indices_inclusive")
        != [FORMAL_DECISION_INDEX_START, 127]
        or sample.get("policy_qualification_indices_inclusive")
        != [128, 159]
        or sample.get("formal_experiment_indices_inclusive")
        != [160, FORMAL_DECISION_INDEX_END]
        or sample.get("outcome_horizons_hours")
        != list(FORMAL_OUTCOME_HORIZONS)
    ):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    return contract, raw


def _artifact(
    bundle_root: Path,
    relative_path: str,
    *,
    media_type: str,
) -> dict[str, object]:
    path = bundle_root / relative_path
    payload = path.read_bytes()
    return {
        "relative_path": relative_path,
        "media_type": media_type,
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _prior_bar_digests(prior_bundle_root: Path) -> dict[str, str]:
    prior = verify_fresh_market_bundle(prior_bundle_root)
    if prior.quality_status is not QualityStatus.PASS:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    dataset = load_json_strict(
        Path(prior_bundle_root) / "normalized" / "dataset.json"
    )
    bars = dataset.get("bars")
    if not isinstance(bars, list):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    result: dict[str, str] = {}
    for item in bars:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("bar_id"), str)
            or not isinstance(item.get("bar_digest"), str)
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        result[item["bar_id"]] = item["bar_digest"]
    return result


def freeze_binance_btcusdt_hourly(
    *,
    output_root: Path,
    bundle_id: str,
    collector: BinanceUsdmFreshCollector | None = None,
    prior_bundle_root: Path | None = None,
    experiment_contract_path: Path = _DEFAULT_EXPERIMENT_CONTRACT,
) -> FreshMarketFreezeResult:
    """Capture, normalize and freeze one formal E0 market dataset."""

    require_id(bundle_id)
    contract, contract_raw = _load_and_validate_experiment_contract(
        experiment_contract_path
    )
    prior_digests = (
        _prior_bar_digests(Path(prior_bundle_root))
        if prior_bundle_root is not None
        else None
    )
    source = (collector or BinanceUsdmFreshCollector()).collect(
        requested_closed_bar_count=FORMAL_REQUESTED_CLOSED_BAR_COUNT
    )
    prepared = prepare_fresh_market_dataset(
        source, prior_bar_digests=prior_digests
    )
    store = FreshMarketWriteOnceStore(
        output_root=Path(output_root), bundle_id=bundle_id
    )
    artifact_paths: list[tuple[str, str]] = []

    store.write_raw("contracts/formal_e0_experiment.json", contract_raw)
    artifact_paths.append(
        ("contracts/formal_e0_experiment.json", "application/json")
    )
    for capture in prepared.requests:
        body = source.raw_body_by_request_id[capture.request_id]
        raw_path = f"raw/{capture.request_id}.body"
        request_path = f"requests/{capture.request_id}.json"
        store.write_raw(raw_path, body)
        store.write_json(request_path, capture.to_dict())
        artifact_paths.extend(
            [
                (raw_path, "application/octet-stream"),
                (request_path, "application/json"),
            ]
        )
    if prior_digests is not None:
        prior_commitment = self_digest(
            {
                "prior_bundle_root": str(
                    Path(prior_bundle_root).resolve()
                ),
                "bar_digests": dict(sorted(prior_digests.items())),
                "commitment_digest": "0" * 64,
            },
            "commitment_digest",
        )
        store.write_json(
            "lineage/prior_bar_digests.json", prior_commitment
        )
        artifact_paths.append(
            ("lineage/prior_bar_digests.json", "application/json")
        )
    store.write_json("receipts/quality.json", prepared.quality.to_dict())
    store.write_json(
        "receipts/replay_admissibility.json",
        prepared.replay_admissibility.to_dict(),
    )
    store.write_json("normalized/dataset.json", prepared.to_dict())
    artifact_paths.extend(
        [
            ("receipts/quality.json", "application/json"),
            ("receipts/replay_admissibility.json", "application/json"),
            ("normalized/dataset.json", "application/json"),
        ]
    )
    artifacts = [
        _artifact(store.bundle_root, path, media_type=media_type)
        for path, media_type in sorted(artifact_paths)
    ]
    manifest = self_digest(
        {
            "schema_id": "theory_agent_v2_fresh_market_bundle",
            "schema_version": "1.0.0",
            "bundle_id": bundle_id,
            "experiment_contract_id": contract["contract_id"],
            "experiment_contract_digest": (
                FORMAL_EXPERIMENT_CONTRACT_DIGEST
            ),
            "provider_id": prepared.provider_id,
            "source_base_url": BINANCE_USDM_BASE_URL,
            "symbol": "BTCUSDT",
            "instrument_type": "PERPETUAL",
            "base_interval": "1h",
            "requested_closed_bar_count": FORMAL_CLOSED_BAR_COUNT,
            "end_time_rule": (
                "FLOOR_OFFICIAL_SERVER_TIME_TO_HOUR_MINUS_1_MILLISECOND"
            ),
            "decision_indices_inclusive": [
                FORMAL_DECISION_INDEX_START,
                FORMAL_DECISION_INDEX_END,
            ],
            "outcome_horizons_hours": list(FORMAL_OUTCOME_HORIZONS),
            "derived_timeframes": ["4h", "1d"],
            "raw_response_storage": "WRITE_ONCE_EXACT_BYTES",
            "availability_status": "DERIVED",
            "availability_basis": "PROVIDER_CLOSED_BAR_PROTOCOL",
            "physical_capture_status": "CAPTURED_NOW",
            "permitted_usage_scope": (
                "HISTORICAL_COUNTERFACTUAL_REPLAY"
            ),
            "contemporaneous_agent_input_status": "UNKNOWN",
            "quality_status": prepared.quality.overall_status.value,
            "quality_receipt_digest": (
                prepared.quality.receipt_digest
            ),
            "replay_admissibility_status": (
                prepared.replay_admissibility.status.value
            ),
            "replay_admissibility_receipt_digest": (
                prepared.replay_admissibility.receipt_digest
            ),
            "prior_bundle_bound": prior_digests is not None,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": (
                EXTERNAL_EXECUTION_AUTHORITY
            ),
            "executable": False,
            "artifacts": artifacts,
            "manifest_digest": "0" * 64,
        },
        "manifest_digest",
    )
    store.write_json("manifest.json", manifest)
    return verify_fresh_market_bundle(store.bundle_root)


def _verify_artifacts(
    bundle_root: Path, artifacts: object
) -> None:
    if not isinstance(artifacts, list) or not artifacts:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    seen: set[str] = set()
    for item in artifacts:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"relative_path", "media_type", "byte_length", "sha256"}
            or not isinstance(item["relative_path"], str)
            or not isinstance(item["media_type"], str)
            or not isinstance(item["byte_length"], int)
            or isinstance(item["byte_length"], bool)
            or not isinstance(item["sha256"], str)
            or item["relative_path"] in seen
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        relative = Path(item["relative_path"])
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        path = bundle_root / relative
        if not path.is_file() or path.is_symlink():
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        payload = path.read_bytes()
        require_digest(item["sha256"])
        if (
            len(payload) != item["byte_length"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        seen.add(item["relative_path"])


def verify_fresh_market_bundle(
    bundle_root: Path,
) -> FreshMarketFreezeResult:
    """Offline, read-only verification with full deterministic re-normalization."""

    supplied_root = Path(bundle_root)
    if supplied_root.is_symlink():
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    root = supplied_root.resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = load_json_strict(manifest_path)
        manifest_digest = verify_self_digest(
            manifest, "manifest_digest"
        )
    except (OSError, ValueError) as exc:
        raise FreshMarketFreezeError(
            "EVIDENCE_LINEAGE_INVALID"
        ) from exc
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    require_id(bundle_id)
    if root.name != bundle_id:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    if (
        manifest.get("experiment_contract_digest")
        != FORMAL_EXPERIMENT_CONTRACT_DIGEST
        or manifest.get("requested_closed_bar_count")
        != FORMAL_CLOSED_BAR_COUNT
        or manifest.get("decision_indices_inclusive")
        != [FORMAL_DECISION_INDEX_START, FORMAL_DECISION_INDEX_END]
        or manifest.get("outcome_horizons_hours")
        != list(FORMAL_OUTCOME_HORIZONS)
        or manifest.get("system_mode") != SYSTEM_MODE
        or manifest.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or manifest.get("executable") is not False
        or manifest.get("permitted_usage_scope")
        != "HISTORICAL_COUNTERFACTUAL_REPLAY"
        or manifest.get("contemporaneous_agent_input_status")
        != "UNKNOWN"
    ):
        raise FreshMarketFreezeError("AUTHORITY_STATUS_MISMATCH")
    _verify_artifacts(root, manifest.get("artifacts"))

    contract_path = root / "contracts" / "formal_e0_experiment.json"
    _load_and_validate_experiment_contract(contract_path)
    request_values: dict[str, PublicRequestCapture] = {}
    raw_by_id: dict[str, bytes] = {}
    for request_path in sorted((root / "requests").glob("*.json")):
        value = load_json_strict(request_path)
        capture = _capture_from_dict(value)
        if capture.request_id in request_values:
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        raw_path = root / "raw" / f"{capture.request_id}.body"
        if (
            not raw_path.is_file()
            or raw_path.is_symlink()
            or _sha256(raw_path) != capture.raw_body_sha256
            or raw_path.stat().st_size != capture.raw_body_byte_length
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        request_values[capture.request_id] = capture
        raw_by_id[capture.request_id] = raw_path.read_bytes()
    required_ids = {
        "binance-usdm-server-time",
        "binance-usdm-exchange-info",
        "binance-usdm-btcusdt-1h-klines",
    }
    if set(request_values) != required_ids:
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    responses = CollectedPublicResponses(
        server_time=request_values["binance-usdm-server-time"],
        exchange_info=request_values["binance-usdm-exchange-info"],
        klines=request_values[
            "binance-usdm-btcusdt-1h-klines"
        ],
        raw_body_by_request_id=raw_by_id,
    )
    prior_path = root / "lineage" / "prior_bar_digests.json"
    prior_digests: Mapping[str, str] | None = None
    if prior_path.exists():
        prior_value = load_json_strict(prior_path)
        verify_self_digest(prior_value, "commitment_digest")
        candidate = prior_value.get("bar_digests")
        if (
            not isinstance(candidate, dict)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                for key, value in candidate.items()
            )
        ):
            raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
        prior_digests = candidate
    if (prior_digests is not None) is not manifest.get(
        "prior_bundle_bound"
    ):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    regenerated = prepare_fresh_market_dataset(
        responses, prior_bar_digests=prior_digests
    )
    dataset = load_json_strict(root / "normalized" / "dataset.json")
    quality = load_json_strict(root / "receipts" / "quality.json")
    admissibility = load_json_strict(
        root / "receipts" / "replay_admissibility.json"
    )
    verify_self_digest(quality, "receipt_digest")
    verify_self_digest(admissibility, "receipt_digest")
    if (
        dataset != regenerated.to_dict()
        or quality != regenerated.quality.to_dict()
        or admissibility
        != regenerated.replay_admissibility.to_dict()
        or manifest.get("quality_status")
        != regenerated.quality.overall_status.value
        or manifest.get("quality_receipt_digest")
        != regenerated.quality.receipt_digest
        or manifest.get("replay_admissibility_status") != "PASS"
        or manifest.get("replay_admissibility_receipt_digest")
        != regenerated.replay_admissibility.receipt_digest
    ):
        raise FreshMarketFreezeError("EVIDENCE_LINEAGE_INVALID")
    return FreshMarketFreezeResult(
        bundle_id=bundle_id,
        bundle_root=root,
        manifest_path=manifest_path,
        manifest_digest=manifest_digest,
        quality_status=regenerated.quality.overall_status,
        closed_bar_count=len(regenerated.bars),
        decision_slot_count=len(regenerated.decision_slots),
        replay_admissibility_status=(
            regenerated.replay_admissibility.status
        ),
    )


__all__ = [
    "FreshMarketFreezeError",
    "FreshMarketFreezeResult",
    "freeze_binance_btcusdt_hourly",
    "verify_fresh_market_bundle",
]
