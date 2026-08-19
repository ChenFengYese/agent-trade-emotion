"""Pure successor-v2 domain logic for missing-data competing-path reviews.

The module has no filesystem, network, account, portfolio, or order authority.
It accepts an already-adapted frozen cycle envelope and emits a deterministic
shadow sidecar.  Missing observations are never imputed; the output only
describes market paths that remain compatible with admitted public evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA_VERSION = "theory-paper-missing-data-inference-sidecar.v2"
FRAMEWORK_ID = "THEORY_PAPER_MISSING_DATA_COMPETING_PATH_FRAMEWORK.v2"
HISTORICAL_MODE = "HISTORICAL_SHADOW_RECONSTRUCTION"
LIVE_MODE = "LIVE_PENDING_ANALYSIS"
SOURCE_MODES = frozenset({HISTORICAL_MODE, LIVE_MODE})

MISSING_KINDS = frozenset(
    {
        "INTERFACE_FAILURE",
        "NOT_COLLECTED",
        "INSUFFICIENT_HISTORY",
        "PUBLICLY_UNIDENTIFIABLE",
    }
)
ORDINALS = (
    "STRONG",
    "MODERATE",
    "WEAK",
    "MIXED",
    "CONTRADICTED",
    "UNKNOWN",
)
REVISIONS = frozenset(
    {
        "NEW",
        "STRENGTHENED",
        "WEAKENED",
        "FALSIFIED",
        "EXPIRED",
        "UNCHANGED",
    }
)
RESIDUAL_PATH_IDS = ("OTHER_PATH", "UNKNOWN_PATH")
TARGET_IDS = (
    "FORCED_DELEVERAGING_EXPLANATION",
    "VISIBLE_LIQUIDITY_RESPONSE",
    "MISSING_HIGHER_TIMEFRAME_BACKGROUND",
    "NEWS_BODY_AND_CAUSALITY",
    "PUBLIC_BEHAVIOR_EXPLANATION_WITH_IDENTITY_UNKNOWN",
)
UNKNOWN = "UNKNOWN"


class InferenceV2Error(ValueError):
    """A stable fail-closed error raised by the successor-v2 domain."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InferenceV2Error("NON_CANONICAL_JSON") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InferenceV2Error("TIMESTAMP_NOT_CANONICAL_UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InferenceV2Error("TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise InferenceV2Error("TIMESTAMP_NOT_AWARE")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise InferenceV2Error("TIMESTAMP_NOT_AWARE")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InferenceV2Error(reason)
    return value


def _list(value: Any, reason: str) -> list[Any]:
    if not isinstance(value, list):
        raise InferenceV2Error(reason)
    return value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value and value != UNKNOWN else None


def _sign(value: float | None) -> int:
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def validate_framework_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("framework_id") != FRAMEWORK_ID:
        raise InferenceV2Error("FRAMEWORK_ID_MISMATCH")
    if config.get("schema_version") != "theory-paper-inference-framework.v2":
        raise InferenceV2Error("FRAMEWORK_SCHEMA_MISMATCH")
    invariants = _mapping(config.get("invariants"), "FRAMEWORK_INVARIANTS_MISSING")
    required_invariants = {
        "available_at_not_after_decision_at": True,
        "missing_is_never_zero": True,
        "imputation_of_unobserved_truth": "FORBIDDEN",
        "minimum_named_competing_paths": 2,
        "correlated_evidence_double_counting": "FORBIDDEN",
        "numeric_probability": "FORBIDDEN",
        "single_causal_winner": "FORBIDDEN",
        "paper_action_authority": "NONE",
        "v1_artifact_mutation": "FORBIDDEN",
    }
    for field, expected in required_invariants.items():
        if invariants.get(field) != expected:
            raise InferenceV2Error(f"FRAMEWORK_INVARIANT_MISMATCH:{field}")
    if tuple(invariants.get("required_residual_nodes", [])) != RESIDUAL_PATH_IDS:
        raise InferenceV2Error("FRAMEWORK_RESIDUAL_NODES_MISMATCH")
    if invariants.get("reader_union_label") != "OTHER_OR_UNKNOWN":
        raise InferenceV2Error("FRAMEWORK_READER_UNION_MISMATCH")
    if set(config.get("missing_kind_registry", [])) != MISSING_KINDS:
        raise InferenceV2Error("FRAMEWORK_MISSING_KIND_REGISTRY_MISMATCH")
    if set(config.get("ordinal_support_registry", [])) != set(ORDINALS):
        raise InferenceV2Error("FRAMEWORK_ORDINAL_REGISTRY_MISMATCH")
    if set(config.get("revision_state_registry", [])) != REVISIONS:
        raise InferenceV2Error("FRAMEWORK_REVISION_REGISTRY_MISMATCH")
    targets = _list(config.get("targets"), "FRAMEWORK_TARGETS_MISSING")
    if [target.get("target_id") for target in targets] != list(TARGET_IDS):
        raise InferenceV2Error("FRAMEWORK_TARGET_REGISTRY_MISMATCH")
    seen_paths: set[str] = set()
    for target in targets:
        row = _mapping(target, "FRAMEWORK_TARGET_INVALID")
        named = _list(row.get("named_paths"), "FRAMEWORK_NAMED_PATHS_MISSING")
        if len(named) < 2:
            raise InferenceV2Error("FRAMEWORK_PATH_CARDINALITY")
        for path in named:
            spec = _mapping(path, "FRAMEWORK_PATH_INVALID")
            path_id = spec.get("path_template_id")
            if not isinstance(path_id, str) or not path_id:
                raise InferenceV2Error("FRAMEWORK_PATH_ID_INVALID")
            if path_id in seen_paths or path_id in RESIDUAL_PATH_IDS:
                raise InferenceV2Error("FRAMEWORK_PATH_ID_DUPLICATE")
            seen_paths.add(path_id)
            for field in (
                "evaluation_strategy",
                "causal_steps",
                "falsifiers",
                "next_observables",
                "expiry_hours",
                "ordinal_cap",
            ):
                if field not in spec:
                    raise InferenceV2Error(f"FRAMEWORK_PATH_FIELD_MISSING:{field}")
            if spec.get("ordinal_cap") not in ORDINALS:
                raise InferenceV2Error("FRAMEWORK_PATH_CAP_INVALID")
            expiry = spec.get("expiry_hours")
            if isinstance(expiry, bool) or not isinstance(expiry, int) or expiry <= 0:
                raise InferenceV2Error("FRAMEWORK_PATH_EXPIRY_INVALID")
    return {
        "valid": True,
        "framework_id": FRAMEWORK_ID,
        "config_digest": canonical_digest(config),
        "target_count": len(targets),
        "named_path_template_count": len(seen_paths),
    }


def _validate_source_analysis(
    source: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], str]:
    run_id = source.get("run_id")
    cycle_id = source.get("cycle_id")
    mode = source.get("mode")
    if not isinstance(run_id, str) or not run_id:
        raise InferenceV2Error("SOURCE_RUN_ID_MISSING")
    if not isinstance(cycle_id, str) or not cycle_id.startswith("cycle-"):
        raise InferenceV2Error("SOURCE_CYCLE_ID_INVALID")
    if mode not in SOURCE_MODES:
        raise InferenceV2Error("SOURCE_MODE_INVALID")
    analysis = _mapping(source.get("analysis"), "SOURCE_ANALYSIS_MISSING")
    market = _mapping(source.get("market"), "SOURCE_MARKET_MISSING")
    if analysis.get("schema_version") != "theory-paper-cycle-analysis.v1":
        raise InferenceV2Error("SOURCE_ANALYSIS_SCHEMA_MISMATCH")
    if market.get("schema_version") != "theory-paper-market-snapshot.v1":
        raise InferenceV2Error("SOURCE_MARKET_SCHEMA_MISMATCH")
    if analysis.get("cycle_id") != cycle_id:
        raise InferenceV2Error("SOURCE_CYCLE_ID_MISMATCH")
    decision_at = analysis.get("decision_at")
    decision_time = parse_utc(decision_at)
    market_observed = parse_utc(market.get("observed_at"))
    if market_observed > decision_time:
        raise InferenceV2Error("SOURCE_MARKET_FROM_FUTURE")
    if analysis.get("market_snapshot_digest") != market.get("market_snapshot_digest"):
        raise InferenceV2Error("SOURCE_MARKET_BINDING_MISMATCH")
    market_candidate = {
        "observed_at": market.get("observed_at"),
        "symbols": [
            _mapping(item, "SOURCE_MARKET_SYMBOL_INVALID").get("raw_digest")
            for item in _list(market.get("symbols"), "SOURCE_MARKET_SYMBOLS_MISSING")
        ],
        "failures": market.get("failures"),
    }
    if canonical_digest(market_candidate) != market.get("market_snapshot_digest"):
        raise InferenceV2Error("SOURCE_MARKET_DIGEST_MISMATCH")
    analysis_candidate = copy.deepcopy(dict(analysis))
    claimed_analysis_digest = analysis_candidate.pop("analysis_digest", None)
    analysis_candidate.pop("theory_integrity_score", None)
    if canonical_digest(analysis_candidate) != claimed_analysis_digest:
        raise InferenceV2Error("SOURCE_ANALYSIS_DIGEST_MISMATCH")
    analysis_symbols = _list(analysis.get("symbols"), "SOURCE_ANALYSIS_SYMBOLS_MISSING")
    market_symbols = _list(market.get("symbols"), "SOURCE_MARKET_SYMBOLS_MISSING")
    analysis_names = [item.get("symbol") for item in analysis_symbols if isinstance(item, Mapping)]
    market_names = [item.get("symbol") for item in market_symbols if isinstance(item, Mapping)]
    if (
        not analysis_names
        or len(analysis_names) != len(set(analysis_names))
        or analysis_names != market_names
    ):
        raise InferenceV2Error("SOURCE_SYMBOL_SET_MISMATCH")
    for item in analysis_symbols:
        row = _mapping(item, "SOURCE_ANALYSIS_SYMBOL_INVALID")
        measurement = _mapping(
            row.get("measurement_snapshot"), "SOURCE_MEASUREMENT_MISSING"
        )
        if parse_utc(measurement.get("observed_at")) > decision_time:
            raise InferenceV2Error("SOURCE_MEASUREMENT_FROM_FUTURE")
    return analysis, market, str(decision_at)


def _pointer(symbol_index: int, suffix: str) -> str:
    return f"/symbols/{symbol_index}/{suffix.lstrip('/')}"


def _missing_item(
    *,
    run_id: str,
    symbol: str,
    target_ids: Sequence[str],
    field_path: str,
    missing_kind: str,
    reason_code: str,
    source_status: str,
    forbidden_claims: Sequence[str],
) -> dict[str, Any]:
    if missing_kind not in MISSING_KINDS:
        raise InferenceV2Error("MISSING_KIND_INVALID")
    base: dict[str, Any] = {
        "run_id": run_id,
        "symbol": symbol,
        "target_ids": list(target_ids),
        "field_path": field_path,
        "missing_kind": missing_kind,
        "reason_code": reason_code,
        "source_status": source_status,
        "allowed_inference": "COMPETING_PATH_COMPATIBILITY_ONLY",
        "forbidden_claims": list(forbidden_claims),
        "imputation_status": "FORBIDDEN_NOT_PERFORMED",
    }
    base["missing_id"] = "MD-" + canonical_digest(base)[:20]
    return base


def _collect_missing_items(
    run_id: str,
    symbol_analysis: Mapping[str, Any],
    symbol_index: int,
) -> list[dict[str, Any]]:
    symbol = str(symbol_analysis.get("symbol"))
    measurement = _mapping(
        symbol_analysis.get("measurement_snapshot"), "MEASUREMENT_MISSING"
    )
    axes = _mapping(measurement.get("axes"), "MEASUREMENT_AXES_MISSING")
    quality = _mapping(measurement.get("data_quality"), "MEASUREMENT_QUALITY_MISSING")
    items: list[dict[str, Any]] = []

    f_axis = _mapping(axes.get("F"), "F_AXIS_MISSING")
    f_fields = f_axis.get("missing_fields", [])
    if isinstance(f_fields, list):
        errors = quality.get("errors")
        interface_failed = isinstance(errors, Mapping) and "liquidations" in errors
        for field in f_fields:
            if not isinstance(field, str):
                continue
            items.append(
                _missing_item(
                    run_id=run_id,
                    symbol=symbol,
                    target_ids=["FORCED_DELEVERAGING_EXPLANATION"],
                    field_path=_pointer(
                        symbol_index,
                        f"measurement_snapshot/axes/F/observations/{field}",
                    ),
                    missing_kind=(
                        "INTERFACE_FAILURE" if interface_failed else "NOT_COLLECTED"
                    ),
                    reason_code=(
                        "PUBLIC_LIQUIDATION_INTERFACE_FAILED"
                        if interface_failed
                        else "FORCE_ORDER_STREAM_NOT_COLLECTED"
                    ),
                    source_status=str(f_axis.get("status", UNKNOWN)),
                    forbidden_claims=(
                        "MISSING_EQUALS_ZERO",
                        "COMPLETE_LIQUIDATION_LEDGER",
                        "FORCED_DELEVERAGING_CAUSAL_TRUTH",
                    ),
                )
            )

    r_axis = _mapping(axes.get("R"), "R_AXIS_MISSING")
    r_fields = r_axis.get("missing_fields", [])
    if isinstance(r_fields, list):
        for field in r_fields:
            if not isinstance(field, str):
                continue
            items.append(
                _missing_item(
                    run_id=run_id,
                    symbol=symbol,
                    target_ids=["VISIBLE_LIQUIDITY_RESPONSE"],
                    field_path=_pointer(
                        symbol_index,
                        f"measurement_snapshot/axes/R/observations/{field}",
                    ),
                    missing_kind="NOT_COLLECTED",
                    reason_code="TEMPORAL_DEPTH_RECOVERY_SEQUENCE_NOT_COLLECTED",
                    source_status=str(r_axis.get("status", UNKNOWN)),
                    forbidden_claims=(
                        "STRICT_RESILIENCE_TRUTH",
                        "HIDDEN_LIQUIDITY_STATE",
                        "MARKET_MAKER_INTENT",
                    ),
                )
            )

    k_axis = _mapping(axes.get("K"), "K_AXIS_MISSING")
    timeframes = _mapping(k_axis.get("timeframes"), "K_TIMEFRAMES_MISSING")
    for timeframe, frame_value in sorted(timeframes.items()):
        frame = _mapping(frame_value, "K_TIMEFRAME_INVALID")
        missing_fields = frame.get("missing_fields", [])
        if not isinstance(missing_fields, list):
            continue
        for field in missing_fields:
            if not isinstance(field, str):
                continue
            items.append(
                _missing_item(
                    run_id=run_id,
                    symbol=symbol,
                    target_ids=["MISSING_HIGHER_TIMEFRAME_BACKGROUND"],
                    field_path=_pointer(
                        symbol_index,
                        (
                            "measurement_snapshot/axes/K/timeframes/"
                            f"{timeframe}/observations/{field}"
                        ),
                    ),
                    missing_kind="INSUFFICIENT_HISTORY",
                    reason_code=f"CLOSED_{str(timeframe).upper()}_HISTORY_INSUFFICIENT",
                    source_status=str(frame.get("status", UNKNOWN)),
                    forbidden_claims=(
                        "IMPUTED_TECHNICAL_VALUE",
                        "SYNTHETIC_PARENT_TIMEFRAME_TREND",
                    ),
                )
            )

    items.extend(
        [
            _missing_item(
                run_id=run_id,
                symbol=symbol,
                target_ids=["NEWS_BODY_AND_CAUSALITY"],
                field_path=_pointer(
                    symbol_index, "news_context/official_primary_article_body"
                ),
                missing_kind="NOT_COLLECTED",
                reason_code="OFFICIAL_PRIMARY_BODY_NOT_BOUND_AT_DECISION",
                source_status=str(
                    _mapping(symbol_analysis.get("news_context"), "NEWS_CONTEXT_MISSING").get(
                        "status", UNKNOWN
                    )
                ),
                forbidden_claims=(
                    "HEADLINE_AS_ARTICLE_FACT",
                    "HEADLINE_SENTIMENT_TRUTH",
                    "NEWS_CAUSAL_DIRECTION",
                ),
            ),
            _missing_item(
                run_id=run_id,
                symbol=symbol,
                target_ids=["NEWS_BODY_AND_CAUSALITY"],
                field_path=_pointer(symbol_index, "news_context/causal_effect"),
                missing_kind="PUBLICLY_UNIDENTIFIABLE",
                reason_code="OBSERVATIONAL_METADATA_CANNOT_IDENTIFY_CAUSAL_EFFECT",
                source_status="UNIDENTIFIED",
                forbidden_claims=(
                    "CAUSAL_EFFECT",
                    "COUNTERFACTUAL_MARKET_PATH",
                ),
            ),
        ]
    )
    for field, reason in (
        ("participant_identity", "PUBLIC_AGGREGATES_DO_NOT_IDENTIFY_PARTICIPANTS"),
        ("open_close_role", "PUBLIC_AGGREGATES_DO_NOT_RECOVER_TRADE_ROLE"),
        ("psychological_state", "PUBLIC_MARKET_DATA_DO_NOT_OBSERVE_PSYCHOLOGY"),
    ):
        items.append(
            _missing_item(
                run_id=run_id,
                symbol=symbol,
                target_ids=[
                    "PUBLIC_BEHAVIOR_EXPLANATION_WITH_IDENTITY_UNKNOWN"
                ],
                field_path=_pointer(
                    symbol_index, f"actor_behavior_hypotheses/{field}"
                ),
                missing_kind="PUBLICLY_UNIDENTIFIABLE",
                reason_code=reason,
                source_status="UNIDENTIFIED",
                forbidden_claims=(
                    "PERSON_OR_INSTITUTION_IDENTITY",
                    "DETERMINISTIC_OPEN_CLOSE_ROLE",
                    "PSYCHOLOGICAL_TRUTH",
                ),
            )
        )
    return sorted(items, key=lambda item: (item["field_path"], item["reason_code"]))


def _evidence_item(
    *,
    run_id: str,
    cycle_id: str,
    symbol: str,
    observable_id: str,
    source_object_id: str,
    source_artifact_digest: str,
    json_pointer: str,
    value: Any,
    available_at: str,
    decision_at: str,
    dependency_group_id: str,
    interpretation_boundary: str,
    quality: str = "ADMITTED",
) -> dict[str, Any]:
    if parse_utc(available_at) > parse_utc(decision_at):
        raise InferenceV2Error(f"EVIDENCE_FROM_FUTURE:{observable_id}")
    if _finite(value) is None and not isinstance(value, (str, int)):
        raise InferenceV2Error(f"EVIDENCE_VALUE_INVALID:{observable_id}")
    base: dict[str, Any] = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "observable_id": observable_id,
        "source_object_id": source_object_id,
        "source_artifact_digest": source_artifact_digest,
        "json_pointer": json_pointer,
        "available_at": available_at,
        "quality": quality,
        "lineage_root_id": source_artifact_digest,
        "dependency_group_id": dependency_group_id,
        "value": value,
        "value_digest": canonical_digest(value),
        "interpretation_boundary": interpretation_boundary,
    }
    base["evidence_id"] = "EV-" + canonical_digest(base)[:24]
    base["evidence_digest"] = canonical_digest(base)
    return base


def _observation_and_evidence(
    *,
    source: Mapping[str, Any],
    symbol_analysis: Mapping[str, Any],
    symbol_index: int,
    decision_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_id = str(source["run_id"])
    cycle_id = str(source["cycle_id"])
    symbol = str(symbol_analysis["symbol"])
    artifacts = _mapping(source.get("source_artifacts"), "SOURCE_ARTIFACTS_MISSING")
    analysis_artifact_digest = artifacts.get("analysis.json")
    if not isinstance(analysis_artifact_digest, str):
        raise InferenceV2Error("SOURCE_ANALYSIS_ARTIFACT_DIGEST_MISSING")
    measurement = _mapping(
        symbol_analysis.get("measurement_snapshot"), "MEASUREMENT_MISSING"
    )
    axes = _mapping(measurement.get("axes"), "MEASUREMENT_AXES_MISSING")
    observed_at = str(measurement.get("observed_at"))
    parse_utc(observed_at)
    vector: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []

    def add(
        observable_id: str,
        value: Any,
        pointer_suffix: str,
        group: str,
        boundary: str,
        *,
        available_at: str = observed_at,
        source_object_id: str | None = None,
    ) -> None:
        if value == UNKNOWN or value is None:
            return
        if _finite(value) is None and not isinstance(value, str):
            return
        vector[observable_id] = value
        evidence.append(
            _evidence_item(
                run_id=run_id,
                cycle_id=cycle_id,
                symbol=symbol,
                observable_id=observable_id,
                source_object_id=source_object_id
                or str(measurement.get("measurement_snapshot_id")),
                source_artifact_digest=analysis_artifact_digest,
                json_pointer=_pointer(symbol_index, pointer_suffix),
                value=value,
                available_at=available_at,
                decision_at=decision_at,
                dependency_group_id=group,
                interpretation_boundary=boundary,
            )
        )

    axis_specs = (
        (
            "D",
            "D_SHORT_WINDOW_FLOW",
            {
                "signed_taker_imbalance": "D_SIGNED_TAKER_IMBALANCE",
                "hourly_taker_buy_sell_ratio": "D_HOURLY_TAKER_RATIO",
            },
        ),
        (
            "L",
            "L_OPEN_INTEREST",
            {
                "open_interest_contracts": "L_OPEN_INTEREST_CONTRACTS",
                "open_interest_value_1h_change_pct": "L_OI_VALUE_1H_CHANGE_PCT",
            },
        ),
        (
            "C",
            "C_CROWDING_VECTOR",
            {
                "funding_rate": "C_FUNDING_RATE",
                "basis_bps": "C_BASIS_BPS",
                "global_account_long_short_ratio": "C_GLOBAL_LONG_SHORT_RATIO",
                "top_position_long_short_ratio": "C_TOP_POSITION_LONG_SHORT_RATIO",
            },
        ),
        (
            "R",
            "R_VISIBLE_BOOK_SNAPSHOT",
            {
                "spread_bps": "R_SPREAD_BPS",
                "top20_imbalance": "R_TOP20_IMBALANCE",
                "buy_1000_impact_bps": "R_BUY_1000_IMPACT_BPS",
                "sell_1000_impact_bps": "R_SELL_1000_IMPACT_BPS",
            },
        ),
    )
    for axis_name, group, fields in axis_specs:
        axis = _mapping(axes.get(axis_name), f"AXIS_{axis_name}_MISSING")
        observations = _mapping(
            axis.get("observations"), f"AXIS_{axis_name}_OBSERVATIONS_MISSING"
        )
        boundary = str(axis.get("interpretation_boundary", UNKNOWN))
        for field, observable_id in fields.items():
            add(
                observable_id,
                observations.get(field),
                f"measurement_snapshot/axes/{axis_name}/observations/{field}",
                group,
                boundary,
            )

    k_axis = _mapping(axes.get("K"), "K_AXIS_MISSING")
    timeframes = _mapping(k_axis.get("timeframes"), "K_TIMEFRAMES_MISSING")
    group_by_timeframe = {
        "15m": "K_15M_PRICE_RESPONSE",
        "1h": "K_1H_STRUCTURE",
        "4h": "K_4H_STRUCTURE",
        "1d": "K_1D_STRUCTURE",
    }
    for timeframe, group in group_by_timeframe.items():
        frame_value = timeframes.get(timeframe)
        if not isinstance(frame_value, Mapping):
            continue
        frame = frame_value
        observations = _mapping(
            frame.get("observations"), f"K_{timeframe}_OBSERVATIONS_MISSING"
        )
        boundary = str(frame.get("interpretation_boundary", UNKNOWN))
        prefix = timeframe.upper().replace("M", "M").replace("H", "H").replace("D", "D")
        for field, suffix in (
            ("trend_state", "TREND"),
            ("change_1_bar_pct", "CHANGE_1_BAR_PCT"),
            ("relative_volume20", "RELATIVE_VOLUME20"),
            ("efficiency_ratio10", "EFFICIENCY_RATIO10"),
        ):
            add(
                f"K_{prefix}_{suffix}",
                observations.get(field),
                (
                    "measurement_snapshot/axes/K/timeframes/"
                    f"{timeframe}/observations/{field}"
                ),
                group,
                boundary,
            )

    add(
        "REFERENCE_PRICE",
        measurement.get("reference_price"),
        "measurement_snapshot/reference_price",
        "K_15M_PRICE_RESPONSE",
        "REFERENCE_PRICE_IS_A_FROZEN_MARKET_MEASURE_NOT_A_SIGNAL",
    )

    news = _mapping(symbol_analysis.get("news_context"), "NEWS_CONTEXT_MISSING")
    headlines = news.get("headline_metadata")
    headline_rows = (
        [item for item in headlines if isinstance(item, Mapping)]
        if isinstance(headlines, list)
        else []
    )
    latest_retrieved = decision_at
    if headline_rows:
        retrieved_values = [str(item.get("retrieved_at")) for item in headline_rows]
        for retrieved in retrieved_values:
            if parse_utc(retrieved) > parse_utc(decision_at):
                raise InferenceV2Error("NEWS_EVIDENCE_FROM_FUTURE")
        latest_retrieved = max(retrieved_values, key=parse_utc)
    add(
        "NEWS_HEADLINE_COUNT",
        len(headline_rows),
        "news_context/headline_metadata",
        "NEWS_DISCOVERY_METADATA",
        str(news.get("boundary", "HEADLINE_METADATA_ONLY")),
        available_at=latest_retrieved,
        source_object_id=str(symbol_analysis.get("symbol_analysis_id")),
    )
    published_times: list[datetime] = []
    for item in headline_rows:
        published = item.get("published_at")
        try:
            parsed = parse_utc(published)
        except InferenceV2Error:
            continue
        if parsed <= parse_utc(decision_at):
            published_times.append(parsed)
    if published_times:
        latest_age = (
            parse_utc(decision_at) - max(published_times)
        ).total_seconds() / 3600.0
        add(
            "NEWS_LATEST_AGE_HOURS",
            round(latest_age, 6),
            "news_context/headline_metadata",
            "NEWS_DISCOVERY_METADATA",
            "PUBLISHED_AT_IS_EVENT_METADATA; RETRIEVED_AT_CONTROLS_AVAILABILITY",
            available_at=latest_retrieved,
            source_object_id=str(symbol_analysis.get("symbol_analysis_id")),
        )
    return vector, sorted(evidence, key=lambda item: item["observable_id"])


def _evidence_maps(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_observable: dict[str, Mapping[str, Any]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        observable = str(item["observable_id"])
        evidence_id = str(item["evidence_id"])
        if observable in by_observable or evidence_id in by_id:
            raise InferenceV2Error("EVIDENCE_ID_OR_OBSERVABLE_DUPLICATE")
        by_observable[observable] = item
        by_id[evidence_id] = item
    return by_observable, by_id


def _append_if_present(
    destination: list[str],
    by_observable: Mapping[str, Mapping[str, Any]],
    observable_id: str,
) -> None:
    item = by_observable.get(observable_id)
    if item is not None:
        destination.append(str(item["evidence_id"]))


def _path_signal_evaluation(
    strategy: str,
    vector: Mapping[str, Any],
    by_observable: Mapping[str, Mapping[str, Any]],
    *,
    f_axis: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> tuple[list[str], list[str], str]:
    support: list[str] = []
    against: list[str] = []
    falsifier_state = "NOT_OBSERVED"
    d = _finite(vector.get("D_SIGNED_TAKER_IMBALANCE"))
    oi = _finite(vector.get("L_OI_VALUE_1H_CHANGE_PCT"))
    p15 = _finite(vector.get("K_15M_CHANGE_1_BAR_PCT"))
    rvol15 = _finite(vector.get("K_15M_RELATIVE_VOLUME20"))
    spread = _finite(vector.get("R_SPREAD_BPS"))
    buy_impact = _finite(vector.get("R_BUY_1000_IMPACT_BPS"))
    sell_impact = _finite(vector.get("R_SELL_1000_IMPACT_BPS"))
    funding = _finite(vector.get("C_FUNDING_RATE"))
    basis = _finite(vector.get("C_BASIS_BPS"))
    headline_count = _finite(vector.get("NEWS_HEADLINE_COUNT"))
    headline_age = _finite(vector.get("NEWS_LATEST_AGE_HOURS"))
    pressure = d is not None and abs(d) >= 0.08
    aligned_move = (
        pressure
        and p15 is not None
        and abs(p15) >= 0.5
        and _sign(d) == _sign(p15)
    )
    opposed_or_muted_move = (
        pressure
        and p15 is not None
        and (_sign(d) != _sign(p15) or abs(p15) < 0.5)
    )
    max_impact = None
    if buy_impact is not None or sell_impact is not None:
        max_impact = max(
            abs(value)
            for value in (buy_impact, sell_impact)
            if value is not None
        )

    if strategy == "F_FORCED_COMPATIBILITY_V1":
        if pressure:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        elif d is not None:
            _append_if_present(against, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if oi is not None and oi <= -0.5:
            _append_if_present(support, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        elif oi is not None and oi >= 0.5:
            _append_if_present(against, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        if aligned_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif opposed_or_muted_move:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        f_obs = f_axis.get("observations")
        if (
            isinstance(f_obs, Mapping)
            and quality.get("liquidation_zero_certainty") is True
            and _finite(f_obs.get("event_count_lower_bound")) == 0
        ):
            falsifier_state = "TRIGGERED"
    elif strategy == "F_VOLUNTARY_COMPATIBILITY_V1":
        if oi is not None and oi >= 0.5:
            _append_if_present(support, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        elif oi is not None and oi <= -0.5 and aligned_move:
            _append_if_present(against, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        if d is not None and abs(d) < 0.08:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        elif pressure and aligned_move:
            _append_if_present(against, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if p15 is not None and not aligned_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
    elif strategy == "R_ABSORPTION_COMPATIBILITY_V1":
        if pressure:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if opposed_or_muted_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif aligned_move and p15 is not None and abs(p15) >= 1.0:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        if (spread is not None and spread <= 2.0) or (
            max_impact is not None and max_impact <= 5.0
        ):
            _append_if_present(support, by_observable, "R_SPREAD_BPS")
        elif (spread is not None and spread >= 5.0) or (
            max_impact is not None and max_impact >= 10.0
        ):
            _append_if_present(against, by_observable, "R_SPREAD_BPS")
    elif strategy == "R_CONSUMPTION_COMPATIBILITY_V1":
        if pressure:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if aligned_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif opposed_or_muted_move:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        if (spread is not None and spread >= 5.0) or (
            max_impact is not None and max_impact >= 10.0
        ):
            _append_if_present(support, by_observable, "R_SPREAD_BPS")
        elif (spread is not None and spread <= 2.0) or (
            max_impact is not None and max_impact <= 5.0
        ):
            _append_if_present(against, by_observable, "R_SPREAD_BPS")
    elif strategy in {
        "K_CONTINUATION_COMPATIBILITY_V1",
        "K_TRANSIENT_COMPATIBILITY_V1",
    }:
        pairs = (
            ("K_1D_TREND", "K_4H_TREND"),
            ("K_4H_TREND", "K_1H_TREND"),
            ("K_1H_TREND", "K_15M_TREND"),
        )
        alignments: list[tuple[str, str, bool]] = []
        for left_id, right_id in pairs:
            left = _string(vector.get(left_id))
            right = _string(vector.get(right_id))
            if left is None or right is None:
                continue
            comparable = left in {"UP", "DOWN", "RANGE"} and right in {
                "UP",
                "DOWN",
                "RANGE",
            }
            if comparable:
                alignments.append((left_id, right_id, left == right))
        want_alignment = strategy == "K_CONTINUATION_COMPATIBILITY_V1"
        for left_id, right_id, aligned in alignments:
            destination = support if aligned == want_alignment else against
            _append_if_present(destination, by_observable, left_id)
            _append_if_present(destination, by_observable, right_id)
        if rvol15 is not None:
            destination = (
                support
                if (rvol15 >= 1.0) == want_alignment
                else against
            )
            _append_if_present(
                destination, by_observable, "K_15M_RELATIVE_VOLUME20"
            )
    elif strategy == "NEWS_FOLLOWTHROUGH_COMPATIBILITY_V1":
        if headline_count is not None and headline_count > 0:
            _append_if_present(support, by_observable, "NEWS_HEADLINE_COUNT")
        elif headline_count == 0:
            _append_if_present(against, by_observable, "NEWS_HEADLINE_COUNT")
        if (
            p15 is not None
            and abs(p15) >= 1.0
            and rvol15 is not None
            and rvol15 >= 1.2
        ):
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif p15 is not None and abs(p15) < 0.5:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
    elif strategy == "NEWS_NOISE_COMPATIBILITY_V1":
        if headline_count == 0 or (headline_age is not None and headline_age >= 12):
            _append_if_present(support, by_observable, "NEWS_HEADLINE_COUNT")
        elif headline_count is not None and headline_count > 0:
            _append_if_present(against, by_observable, "NEWS_HEADLINE_COUNT")
        if p15 is not None and abs(p15) < 0.5:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif (
            p15 is not None
            and abs(p15) >= 1.0
            and rvol15 is not None
            and rvol15 >= 1.2
        ):
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
    elif strategy == "BEHAVIOR_DIRECTIONAL_COMPATIBILITY_V1":
        if pressure:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        elif d is not None:
            _append_if_present(against, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if oi is not None and oi >= 0.5:
            _append_if_present(support, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        elif oi is not None and oi <= -0.5:
            _append_if_present(against, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        if aligned_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif opposed_or_muted_move:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        crowding_direction = 0
        if funding is not None and funding != 0:
            crowding_direction = _sign(funding)
        if crowding_direction and d is not None:
            destination = (
                support if crowding_direction == _sign(d) else against
            )
            _append_if_present(destination, by_observable, "C_FUNDING_RATE")
    elif strategy == "BEHAVIOR_NON_DIRECTIONAL_COMPATIBILITY_V1":
        if oi is not None and abs(oi) >= 0.5:
            _append_if_present(support, by_observable, "L_OI_VALUE_1H_CHANGE_PCT")
        if d is not None and abs(d) < 0.08:
            _append_if_present(support, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        elif pressure and aligned_move:
            _append_if_present(against, by_observable, "D_SIGNED_TAKER_IMBALANCE")
        if (funding is not None and abs(funding) >= 0.0001) or (
            basis is not None and abs(basis) >= 5.0
        ):
            _append_if_present(support, by_observable, "C_FUNDING_RATE")
        if opposed_or_muted_move:
            _append_if_present(support, by_observable, "K_15M_CHANGE_1_BAR_PCT")
        elif aligned_move:
            _append_if_present(against, by_observable, "K_15M_CHANGE_1_BAR_PCT")
    else:
        raise InferenceV2Error(f"UNKNOWN_EVALUATION_STRATEGY:{strategy}")
    return sorted(set(support)), sorted(set(against)), falsifier_state


def _groups(
    evidence_ids: Sequence[str],
    by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    return sorted(
        {
            str(by_id[evidence_id]["dependency_group_id"])
            for evidence_id in evidence_ids
        }
    )


def _ordinal(
    support_groups: Sequence[str],
    against_groups: Sequence[str],
    cap: str,
) -> str:
    support_count = len(set(support_groups))
    against_count = len(set(against_groups))
    if support_count and against_count:
        return "MIXED"
    if against_count and not support_count:
        return "CONTRADICTED"
    if not support_count:
        return "UNKNOWN"
    base = "STRONG" if support_count >= 3 else "MODERATE" if support_count == 2 else "WEAK"
    rank = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
    if cap in rank and rank[base] > rank[cap]:
        return cap
    return base


def derive_revision_state(
    prior_path: Mapping[str, Any] | None,
    current_path_state: Mapping[str, Any],
    decision_at: str,
) -> dict[str, Any]:
    current_support = set(current_path_state.get("independent_support_groups", []))
    current_against = set(
        current_path_state.get("independent_contradiction_groups", [])
    )
    if prior_path is None:
        state = "NEW"
        prior_digest = None
        prior_support: set[str] = set()
        prior_against: set[str] = set()
    else:
        prior_state = _mapping(
            prior_path.get("path_state"), "PRIOR_PATH_STATE_MISSING"
        )
        prior_digest = prior_path.get("path_state_digest")
        if prior_digest != canonical_digest(prior_state):
            raise InferenceV2Error("PRIOR_PATH_STATE_DIGEST_MISMATCH")
        prior_support = set(prior_state.get("independent_support_groups", []))
        prior_against = set(
            prior_state.get("independent_contradiction_groups", [])
        )
        if current_path_state.get("falsifier_state") == "TRIGGERED":
            state = "FALSIFIED"
        elif parse_utc(prior_state.get("expires_at")) <= parse_utc(decision_at):
            state = "EXPIRED"
        else:
            prior_score = len(prior_support) - len(prior_against)
            current_score = len(current_support) - len(current_against)
            if current_score > prior_score:
                state = "STRENGTHENED"
            elif current_score < prior_score:
                state = "WEAKENED"
            else:
                state = "UNCHANGED"
    receipt: dict[str, Any] = {
        "revision_state": state,
        "previous_path_state_digest": prior_digest,
        "added_support_groups": sorted(current_support - prior_support),
        "removed_support_groups": sorted(prior_support - current_support),
        "added_contradiction_groups": sorted(current_against - prior_against),
        "removed_contradiction_groups": sorted(prior_against - current_against),
        "change_basis": (
            "FALSIFIER_TRIGGERED"
            if state == "FALSIFIED"
            else "PRIOR_EXPIRY_REACHED"
            if state == "EXPIRED"
            else "INDEPENDENT_EVIDENCE_GROUP_DELTA"
            if state in {"STRENGTHENED", "WEAKENED"}
            else "FIRST_ADMISSIBLE_REVISION"
            if state == "NEW"
            else "NO_NET_INDEPENDENT_EVIDENCE_CHANGE"
        ),
    }
    receipt["revision_digest"] = canonical_digest(receipt)
    return receipt


def _path_instance(
    *,
    source: Mapping[str, Any],
    symbol: str,
    target_id: str,
    path_spec: Mapping[str, Any],
    decision_at: str,
    vector: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    f_axis: Mapping[str, Any],
    quality: Mapping[str, Any],
    prior_path: Mapping[str, Any] | None,
    path_kind: str = "NAMED_COMPETING_PATH",
) -> dict[str, Any]:
    path_id = str(path_spec["path_template_id"])
    by_observable, by_id = _evidence_maps(evidence)
    if path_kind == "NAMED_COMPETING_PATH":
        support, against, falsifier_state = _path_signal_evaluation(
            str(path_spec["evaluation_strategy"]),
            vector,
            by_observable,
            f_axis=f_axis,
            quality=quality,
        )
        cap = str(path_spec["ordinal_cap"])
    else:
        support, against, falsifier_state = [], [], "NOT_APPLICABLE"
        cap = "UNKNOWN"
    support_groups = _groups(support, by_id)
    against_groups = _groups(against, by_id)
    ordinal = (
        _ordinal(support_groups, against_groups, cap)
        if path_kind == "NAMED_COMPETING_PATH"
        else "UNKNOWN"
    )
    expires_at = iso_utc(
        parse_utc(decision_at)
        + timedelta(hours=int(path_spec.get("expiry_hours", 8)))
    )
    stable_identity = {
        "run_id": source["run_id"],
        "symbol": symbol,
        "target_id": target_id,
        "path_template_id": path_id,
    }
    path_state: dict[str, Any] = {
        "path_instance_id": "PI-" + canonical_digest(stable_identity)[:24],
        "path_revision_id": "PR-"
        + canonical_digest({**stable_identity, "cycle_id": source["cycle_id"]})[:24],
        "path_template_id": path_id,
        "path_kind": path_kind,
        "label_zh": path_spec.get("label_zh"),
        "truth_status": (
            "OBSERVATIONALLY_COMPATIBLE_NOT_CAUSAL_TRUTH"
            if path_kind == "NAMED_COMPETING_PATH"
            else "RESIDUAL_OR_EPISTEMIC_GUARD"
        ),
        "causal_steps": list(path_spec.get("causal_steps", [])),
        "support_evidence_ids": support,
        "contradiction_evidence_ids": against,
        "independent_support_groups": support_groups,
        "independent_contradiction_groups": against_groups,
        "support_ordinal": ordinal,
        "falsifiers": list(path_spec.get("falsifiers", [])),
        "falsifier_state": falsifier_state,
        "next_observables": list(path_spec.get("next_observables", [])),
        "expires_at": expires_at,
        "probability_status": "FORBIDDEN_NOT_CALIBRATED",
        "selection_status": "NO_SINGLE_CAUSAL_WINNER",
    }
    path_state_digest = canonical_digest(path_state)
    revision = derive_revision_state(prior_path, path_state, decision_at)
    result: dict[str, Any] = {
        "path_state": path_state,
        "path_state_digest": path_state_digest,
        "revision": revision,
    }
    result["path_record_digest"] = canonical_digest(result)
    return result


def _target_active(target_id: str, missing_items: Sequence[Mapping[str, Any]]) -> bool:
    return any(target_id in item.get("target_ids", []) for item in missing_items)


def _prior_path_map(
    prior_target: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if prior_target is None:
        return {}
    paths = _list(prior_target.get("paths"), "PRIOR_TARGET_PATHS_MISSING")
    result: dict[str, Mapping[str, Any]] = {}
    for path in paths:
        row = _mapping(path, "PRIOR_PATH_INVALID")
        state = _mapping(row.get("path_state"), "PRIOR_PATH_STATE_MISSING")
        path_id = state.get("path_template_id")
        if not isinstance(path_id, str) or path_id in result:
            raise InferenceV2Error("PRIOR_PATH_ID_INVALID")
        result[path_id] = row
    return result


def _target_review(
    *,
    source: Mapping[str, Any],
    config_target: Mapping[str, Any],
    symbol: str,
    decision_at: str,
    vector: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    missing_items: Sequence[Mapping[str, Any]],
    f_axis: Mapping[str, Any],
    quality: Mapping[str, Any],
    prior_target: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target_id = str(config_target["target_id"])
    prior_paths = _prior_path_map(prior_target)
    paths: list[dict[str, Any]] = []
    for spec_value in _list(
        config_target.get("named_paths"), "TARGET_NAMED_PATHS_MISSING"
    ):
        spec = _mapping(spec_value, "TARGET_PATH_SPEC_INVALID")
        path_id = str(spec["path_template_id"])
        paths.append(
            _path_instance(
                source=source,
                symbol=symbol,
                target_id=target_id,
                path_spec=spec,
                decision_at=decision_at,
                vector=vector,
                evidence=evidence,
                f_axis=f_axis,
                quality=quality,
                prior_path=prior_paths.get(path_id),
            )
        )
    residual_specs = (
        {
            "path_template_id": "OTHER_PATH",
            "label_zh": "已观察但未被已注册路径覆盖的其他解释",
            "causal_steps": [
                "保留已观察结果",
                "拒绝强制归入命名路径",
            ],
            "falsifiers": [
                "新增独立证据使已注册路径完整覆盖当前观测"
            ],
            "next_observables": [
                "可区分已注册路径与未建模解释的独立观测"
            ],
            "expiry_hours": 8,
        },
        {
            "path_template_id": "UNKNOWN_PATH",
            "label_zh": "证据不足或公开不可识别",
            "causal_steps": [
                "保留缺口及其类型",
                "不把未知转成市场结果或事实",
            ],
            "falsifiers": [
                "合规且时点有效的新证据关闭对应识别缺口"
            ],
            "next_observables": [
                "关闭当前缺口所需的正规数据或独立观测"
            ],
            "expiry_hours": 8,
        },
    )
    for residual in residual_specs:
        path_id = str(residual["path_template_id"])
        paths.append(
            _path_instance(
                source=source,
                symbol=symbol,
                target_id=target_id,
                path_spec=residual,
                decision_at=decision_at,
                vector=vector,
                evidence=evidence,
                f_axis=f_axis,
                quality=quality,
                prior_path=prior_paths.get(path_id),
                path_kind=(
                    "UNMODELED_EXPLANATION_RESIDUAL"
                    if path_id == "OTHER_PATH"
                    else "EPISTEMIC_META_NODE"
                ),
            )
        )
    relevant_missing = [
        item["missing_id"]
        for item in missing_items
        if target_id in item.get("target_ids", [])
    ]
    target: dict[str, Any] = {
        "target_id": target_id,
        "target_instance_id": "TI-"
        + canonical_digest(
            {
                "run_id": source["run_id"],
                "symbol": symbol,
                "target_id": target_id,
            }
        )[:24],
        "status": "ACTIVE_HYPOTHESIS_ONLY",
        "target_boundary": config_target.get("target_boundary"),
        "missing_item_ids": relevant_missing,
        "paths": paths,
        "residual_nodes": {
            "market_or_explanation_residual": "OTHER_PATH",
            "epistemic_unknown": "UNKNOWN_PATH",
            "reader_union_label": "OTHER_OR_UNKNOWN",
        },
        "decision_effect": "CONTEXT_ONLY_CANNOT_BYPASS_V1_RISK_OR_ACTION_GATES",
    }
    target["target_digest"] = canonical_digest(target)
    return target


def _observation_delta(
    prior_vector: Mapping[str, Any] | None,
    current_vector: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if prior_vector is None:
        return []
    rows: list[dict[str, Any]] = []
    for observable_id in sorted(set(prior_vector) | set(current_vector)):
        before = prior_vector.get(observable_id, UNKNOWN)
        after = current_vector.get(observable_id, UNKNOWN)
        if before == after:
            continue
        before_number = _finite(before)
        after_number = _finite(after)
        row: dict[str, Any] = {
            "observable_id": observable_id,
            "before": before,
            "after": after,
            "change_type": "VALUE_CHANGED",
        }
        if before_number is not None and after_number is not None:
            row["numeric_delta"] = round(after_number - before_number, 12)
        rows.append(row)
    return rows


def _prior_symbol_map(
    previous_sidecar: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if previous_sidecar is None:
        return {}
    symbols = _list(previous_sidecar.get("symbols"), "PRIOR_SYMBOLS_MISSING")
    result: dict[str, Mapping[str, Any]] = {}
    for item in symbols:
        row = _mapping(item, "PRIOR_SYMBOL_INVALID")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol in result:
            raise InferenceV2Error("PRIOR_SYMBOL_DUPLICATE")
        result[symbol] = row
    return result


def build_cycle_sidecar(
    source: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_sidecar: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic, non-authoritative missing-data sidecar."""

    config_result = validate_framework_config(config)
    analysis, market, decision_at = _validate_source_analysis(source)
    if previous_sidecar is not None:
        validate_sidecar(previous_sidecar, config, allow_unresolved_prior=True)
        if previous_sidecar.get("source", {}).get("run_id") != source.get("run_id"):
            raise InferenceV2Error("PRIOR_RUN_ID_MISMATCH")
        if parse_utc(previous_sidecar.get("source", {}).get("decision_at")) >= parse_utc(
            decision_at
        ):
            raise InferenceV2Error("PRIOR_DECISION_TIME_NOT_EARLIER")
    prior_symbols = _prior_symbol_map(previous_sidecar)
    config_targets = {
        str(target["target_id"]): target
        for target in _list(config.get("targets"), "FRAMEWORK_TARGETS_MISSING")
        if isinstance(target, Mapping)
    }
    symbol_rows: list[dict[str, Any]] = []
    all_evidence_count = 0
    for index, symbol_value in enumerate(
        _list(analysis.get("symbols"), "SOURCE_ANALYSIS_SYMBOLS_MISSING")
    ):
        symbol_analysis = _mapping(symbol_value, "SOURCE_ANALYSIS_SYMBOL_INVALID")
        symbol = str(symbol_analysis.get("symbol"))
        missing_items = _collect_missing_items(
            str(source["run_id"]), symbol_analysis, index
        )
        vector, evidence = _observation_and_evidence(
            source=source,
            symbol_analysis=symbol_analysis,
            symbol_index=index,
            decision_at=decision_at,
        )
        all_evidence_count += len(evidence)
        measurement = _mapping(
            symbol_analysis.get("measurement_snapshot"), "MEASUREMENT_MISSING"
        )
        axes = _mapping(measurement.get("axes"), "MEASUREMENT_AXES_MISSING")
        f_axis = _mapping(axes.get("F"), "F_AXIS_MISSING")
        quality = _mapping(
            measurement.get("data_quality"), "MEASUREMENT_QUALITY_MISSING"
        )
        prior_symbol = prior_symbols.get(symbol)
        prior_targets: dict[str, Mapping[str, Any]] = {}
        prior_vector: Mapping[str, Any] | None = None
        if prior_symbol is not None:
            prior_vector = _mapping(
                prior_symbol.get("observation_vector"), "PRIOR_VECTOR_MISSING"
            )
            for target_value in _list(
                prior_symbol.get("inference_targets"), "PRIOR_TARGETS_MISSING"
            ):
                target = _mapping(target_value, "PRIOR_TARGET_INVALID")
                target_id = target.get("target_id")
                if not isinstance(target_id, str) or target_id in prior_targets:
                    raise InferenceV2Error("PRIOR_TARGET_ID_INVALID")
                prior_targets[target_id] = target
        targets: list[dict[str, Any]] = []
        for target_id in TARGET_IDS:
            if not _target_active(target_id, missing_items):
                continue
            targets.append(
                _target_review(
                    source=source,
                    config_target=config_targets[target_id],
                    symbol=symbol,
                    decision_at=decision_at,
                    vector=vector,
                    evidence=evidence,
                    missing_items=missing_items,
                    f_axis=f_axis,
                    quality=quality,
                    prior_target=prior_targets.get(target_id),
                )
            )
        symbol_row: dict[str, Any] = {
            "symbol": symbol,
            "source_symbol_analysis_id": symbol_analysis.get("symbol_analysis_id"),
            "source_measurement_snapshot_id": measurement.get(
                "measurement_snapshot_id"
            ),
            "source_measurement_observed_at": measurement.get("observed_at"),
            "missing_data_register": missing_items,
            "evidence_register": evidence,
            "observation_vector": vector,
            "observation_delta_from_prior_cycle": _observation_delta(
                prior_vector, vector
            ),
            "inference_targets": targets,
            "review_flow": [
                "GAP_DEFINED",
                "EVIDENCE_ADMITTED",
                "COMPETING_PATHS_ASSESSED",
                "SUPPORT_AND_COUNTEREVIDENCE_RECORDED",
                "PRIOR_REVISION_COMPARED",
                "FALSIFIER_AND_NEXT_OBSERVATION_REGISTERED",
                "DECISION_BOUNDARY_ENFORCED",
            ],
        }
        symbol_row["symbol_review_digest"] = canonical_digest(symbol_row)
        symbol_rows.append(symbol_row)

    previous_digest = (
        previous_sidecar.get("sidecar_digest")
        if previous_sidecar is not None
        else None
    )
    artifacts = _mapping(source.get("source_artifacts"), "SOURCE_ARTIFACTS_MISSING")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "framework_id": FRAMEWORK_ID,
        "framework_config_digest": config_result["config_digest"],
        "mode": source["mode"],
        "execution_scope": "PUBLIC_DATA_PAPER_CONTEXT_ONLY",
        "source": {
            "run_id": source["run_id"],
            "cycle_id": source["cycle_id"],
            "decision_at": decision_at,
            "market_observed_at": market.get("observed_at"),
            "source_committed_at": source.get("source_committed_at"),
            "source_artifacts": dict(sorted(artifacts.items())),
            "analysis_internal_digest": analysis.get("analysis_digest"),
            "market_snapshot_digest": market.get("market_snapshot_digest"),
            "physical_existence_at_source_time": (
                "NOT_CLAIMED"
                if source["mode"] == HISTORICAL_MODE
                else "REQUIRED_BY_ACTIVATED_LIVE_RUNTIME"
            ),
        },
        "point_in_time": {
            "decision_at": decision_at,
            "admitted_evidence_count": all_evidence_count,
            "future_evidence_violations": [],
            "rule": "EVERY_EVIDENCE_AVAILABLE_AT_NOT_AFTER_DECISION_AT",
        },
        "symbols": symbol_rows,
        "previous_sidecar_digest": previous_digest,
        "boundaries": [
            "MISSING_VALUES_ARE_NOT_IMPUTED",
            "PATH_SUPPORT_IS_ORDINAL_NOT_PROBABILITY",
            "COMPATIBILITY_IS_NOT_CAUSAL_TRUTH",
            "OTHER_PATH_AND_UNKNOWN_PATH_REMAIN_SEPARATE",
            "PARTICIPANT_IDENTITY_AND_PSYCHOLOGY_REMAIN_UNKNOWN",
            "SIDECAR_HAS_NO_ACTION_OR_RISK_GATE_AUTHORITY",
            "V1_ARTIFACTS_ARE_READ_ONLY",
        ],
        "activation_state": {
            "shadow_write": "ENABLED_FOR_VALIDATION",
            "shadow_consume": "DISABLED",
            "may_change_v1_decision": False,
            "may_bypass_v1_risk_gate": False,
            "existing_automation_switched": False,
        },
    }
    result["sidecar_digest"] = canonical_digest(result)
    validate_sidecar(result, config, previous_sidecar)
    return result


def validate_sidecar(
    sidecar: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_sidecar: Mapping[str, Any] | None = None,
    *,
    allow_unresolved_prior: bool = False,
) -> dict[str, Any]:
    """Validate all successor-v2 invariants and return a compact verdict."""

    config_verdict = validate_framework_config(config)
    if sidecar.get("schema_version") != SCHEMA_VERSION:
        raise InferenceV2Error("SIDECAR_SCHEMA_MISMATCH")
    if sidecar.get("framework_id") != FRAMEWORK_ID:
        raise InferenceV2Error("SIDECAR_FRAMEWORK_MISMATCH")
    if sidecar.get("mode") not in SOURCE_MODES:
        raise InferenceV2Error("SIDECAR_MODE_INVALID")
    if sidecar.get("framework_config_digest") != config_verdict["config_digest"]:
        raise InferenceV2Error("SIDECAR_CONFIG_DIGEST_MISMATCH")
    supplied_digest = sidecar.get("sidecar_digest")
    unsigned = copy.deepcopy(dict(sidecar))
    unsigned.pop("sidecar_digest", None)
    if supplied_digest != canonical_digest(unsigned):
        raise InferenceV2Error("SIDECAR_DIGEST_MISMATCH")
    source = _mapping(sidecar.get("source"), "SIDECAR_SOURCE_MISSING")
    decision_at = source.get("decision_at")
    parse_utc(decision_at)
    if (
        not isinstance(source.get("run_id"), str)
        or not isinstance(source.get("cycle_id"), str)
        or not isinstance(source.get("source_artifacts"), Mapping)
        or "analysis.json" not in source["source_artifacts"]
        or "market.json" not in source["source_artifacts"]
    ):
        raise InferenceV2Error("SIDECAR_SOURCE_BINDING_INVALID")
    prior_symbols: dict[str, Mapping[str, Any]] = {}
    if previous_sidecar is not None:
        prior_digest = previous_sidecar.get("sidecar_digest")
        if sidecar.get("previous_sidecar_digest") != prior_digest:
            raise InferenceV2Error("SIDECAR_PRIOR_DIGEST_MISMATCH")
        prior_source = _mapping(
            previous_sidecar.get("source"), "SIDECAR_PRIOR_SOURCE_MISSING"
        )
        if prior_source.get("run_id") != source.get("run_id"):
            raise InferenceV2Error("SIDECAR_PRIOR_RUN_MISMATCH")
        try:
            current_number = int(str(source.get("cycle_id")).split("-", 1)[1])
            prior_number = int(str(prior_source.get("cycle_id")).split("-", 1)[1])
        except (IndexError, ValueError) as exc:
            raise InferenceV2Error("SIDECAR_CYCLE_ID_INVALID") from exc
        if current_number != prior_number + 1:
            raise InferenceV2Error("SIDECAR_PRIOR_CYCLE_NOT_ADJACENT")
        if parse_utc(prior_source.get("decision_at")) >= parse_utc(decision_at):
            raise InferenceV2Error("SIDECAR_PRIOR_TIME_NOT_EARLIER")
        prior_symbols = _prior_symbol_map(previous_sidecar)
    elif (
        sidecar.get("previous_sidecar_digest") is not None
        and not allow_unresolved_prior
    ):
        raise InferenceV2Error("SIDECAR_UNEXPECTED_PRIOR_DIGEST")
    symbols = _list(sidecar.get("symbols"), "SIDECAR_SYMBOLS_MISSING")
    config_path_specs: dict[str, Mapping[str, Any]] = {}
    for target_value in _list(config.get("targets"), "FRAMEWORK_TARGETS_MISSING"):
        target_spec = _mapping(target_value, "FRAMEWORK_TARGET_INVALID")
        for path_value in _list(
            target_spec.get("named_paths"), "FRAMEWORK_NAMED_PATHS_MISSING"
        ):
            path_spec = _mapping(path_value, "FRAMEWORK_PATH_INVALID")
            config_path_specs[str(path_spec["path_template_id"])] = path_spec
    symbol_names: set[str] = set()
    evidence_count = 0
    target_count = 0
    for symbol_value in symbols:
        symbol = _mapping(symbol_value, "SIDECAR_SYMBOL_INVALID")
        name = symbol.get("symbol")
        if not isinstance(name, str) or name in symbol_names:
            raise InferenceV2Error("SIDECAR_SYMBOL_DUPLICATE")
        symbol_names.add(name)
        missing_items = _list(
            symbol.get("missing_data_register"), "SIDECAR_MISSING_REGISTER_INVALID"
        )
        missing_ids: set[str] = set()
        for item_value in missing_items:
            item = _mapping(item_value, "SIDECAR_MISSING_ITEM_INVALID")
            missing_id = item.get("missing_id")
            if not isinstance(missing_id, str) or missing_id in missing_ids:
                raise InferenceV2Error("SIDECAR_MISSING_ID_DUPLICATE")
            missing_ids.add(missing_id)
            if item.get("missing_kind") not in MISSING_KINDS:
                raise InferenceV2Error("SIDECAR_MISSING_KIND_INVALID")
            if item.get("imputation_status") != "FORBIDDEN_NOT_PERFORMED":
                raise InferenceV2Error("SIDECAR_MISSING_VALUE_IMPUTED")
        evidence = _list(
            symbol.get("evidence_register"), "SIDECAR_EVIDENCE_REGISTER_INVALID"
        )
        _, by_id = _evidence_maps(
            [_mapping(item, "SIDECAR_EVIDENCE_ITEM_INVALID") for item in evidence]
        )
        evidence_count += len(evidence)
        for item in evidence:
            row = _mapping(item, "SIDECAR_EVIDENCE_ITEM_INVALID")
            if parse_utc(row.get("available_at")) > parse_utc(decision_at):
                raise InferenceV2Error("SIDECAR_EVIDENCE_FROM_FUTURE")
            candidate = dict(row)
            evidence_digest = candidate.pop("evidence_digest", None)
            if evidence_digest != canonical_digest(candidate):
                raise InferenceV2Error("SIDECAR_EVIDENCE_DIGEST_MISMATCH")
        targets = _list(
            symbol.get("inference_targets"), "SIDECAR_TARGETS_INVALID"
        )
        prior_targets: dict[str, Mapping[str, Any]] = {}
        if name in prior_symbols:
            for prior_target_value in _list(
                prior_symbols[name].get("inference_targets"),
                "SIDECAR_PRIOR_TARGETS_INVALID",
            ):
                prior_target = _mapping(
                    prior_target_value, "SIDECAR_PRIOR_TARGET_INVALID"
                )
                prior_target_id = prior_target.get("target_id")
                if not isinstance(prior_target_id, str):
                    raise InferenceV2Error("SIDECAR_PRIOR_TARGET_ID_INVALID")
                prior_targets[prior_target_id] = prior_target
        target_ids: set[str] = set()
        for target_value in targets:
            target = _mapping(target_value, "SIDECAR_TARGET_INVALID")
            target_id = target.get("target_id")
            if target_id not in TARGET_IDS or target_id in target_ids:
                raise InferenceV2Error("SIDECAR_TARGET_ID_INVALID")
            target_ids.add(str(target_id))
            target_count += 1
            if (
                target.get("status") != "ACTIVE_HYPOTHESIS_ONLY"
                or target.get("decision_effect")
                != "CONTEXT_ONLY_CANNOT_BYPASS_V1_RISK_OR_ACTION_GATES"
            ):
                raise InferenceV2Error("SIDECAR_TARGET_AUTHORITY_INVALID")
            if not set(target.get("missing_item_ids", [])).issubset(missing_ids):
                raise InferenceV2Error("SIDECAR_TARGET_MISSING_REF_INVALID")
            if not target.get("missing_item_ids"):
                raise InferenceV2Error("SIDECAR_TARGET_WITHOUT_GAP")
            paths = _list(target.get("paths"), "SIDECAR_PATHS_INVALID")
            prior_path_lookup = _prior_path_map(prior_targets.get(str(target_id)))
            path_ids: set[str] = set()
            named_count = 0
            for path_value in paths:
                path = _mapping(path_value, "SIDECAR_PATH_INVALID")
                state = _mapping(path.get("path_state"), "SIDECAR_PATH_STATE_INVALID")
                path_id = state.get("path_template_id")
                if not isinstance(path_id, str) or path_id in path_ids:
                    raise InferenceV2Error("SIDECAR_PATH_ID_DUPLICATE")
                path_ids.add(path_id)
                if state.get("path_kind") == "NAMED_COMPETING_PATH":
                    named_count += 1
                    spec = config_path_specs.get(path_id)
                    if spec is None:
                        raise InferenceV2Error("SIDECAR_PATH_TEMPLATE_UNKNOWN")
                    expected_ordinal = _ordinal(
                        state.get("independent_support_groups", []),
                        state.get("independent_contradiction_groups", []),
                        str(spec.get("ordinal_cap")),
                    )
                    if state.get("support_ordinal") != expected_ordinal:
                        raise InferenceV2Error("SIDECAR_PATH_ORDINAL_MISMATCH")
                elif path_id == "OTHER_PATH":
                    if state.get("path_kind") != "UNMODELED_EXPLANATION_RESIDUAL":
                        raise InferenceV2Error("SIDECAR_OTHER_PATH_KIND_INVALID")
                elif path_id == "UNKNOWN_PATH":
                    if state.get("path_kind") != "EPISTEMIC_META_NODE":
                        raise InferenceV2Error("SIDECAR_UNKNOWN_PATH_KIND_INVALID")
                else:
                    raise InferenceV2Error("SIDECAR_PATH_KIND_INVALID")
                if state.get("support_ordinal") not in ORDINALS:
                    raise InferenceV2Error("SIDECAR_PATH_ORDINAL_INVALID")
                if state.get("probability_status") != "FORBIDDEN_NOT_CALIBRATED":
                    raise InferenceV2Error("SIDECAR_PATH_PROBABILITY_INVALID")
                if "probability" in state:
                    raise InferenceV2Error("SIDECAR_NUMERIC_PROBABILITY_FORBIDDEN")
                support_ids = state.get("support_evidence_ids", [])
                against_ids = state.get("contradiction_evidence_ids", [])
                if not isinstance(support_ids, list) or not isinstance(against_ids, list):
                    raise InferenceV2Error("SIDECAR_PATH_EVIDENCE_REFS_INVALID")
                if not set(support_ids + against_ids).issubset(by_id):
                    raise InferenceV2Error("SIDECAR_PATH_EVIDENCE_REF_UNKNOWN")
                support_groups = _groups(support_ids, by_id)
                against_groups = _groups(against_ids, by_id)
                if support_groups != state.get("independent_support_groups"):
                    raise InferenceV2Error("SIDECAR_SUPPORT_GROUP_MISMATCH")
                if against_groups != state.get("independent_contradiction_groups"):
                    raise InferenceV2Error("SIDECAR_CONTRADICTION_GROUP_MISMATCH")
                if not state.get("causal_steps") or not state.get("falsifiers"):
                    raise InferenceV2Error("SIDECAR_PATH_TESTABILITY_MISSING")
                if not state.get("next_observables"):
                    raise InferenceV2Error("SIDECAR_NEXT_OBSERVATION_MISSING")
                if parse_utc(state.get("expires_at")) <= parse_utc(decision_at):
                    raise InferenceV2Error("SIDECAR_PATH_EXPIRY_INVALID")
                if path.get("path_state_digest") != canonical_digest(state):
                    raise InferenceV2Error("SIDECAR_PATH_STATE_DIGEST_MISMATCH")
                revision = _mapping(
                    path.get("revision"), "SIDECAR_REVISION_INVALID"
                )
                if revision.get("revision_state") not in REVISIONS:
                    raise InferenceV2Error("SIDECAR_REVISION_STATE_INVALID")
                revision_candidate = dict(revision)
                revision_digest = revision_candidate.pop("revision_digest", None)
                if revision_digest != canonical_digest(revision_candidate):
                    raise InferenceV2Error("SIDECAR_REVISION_DIGEST_MISMATCH")
                if previous_sidecar is not None or sidecar.get(
                    "previous_sidecar_digest"
                ) is None:
                    expected_revision = derive_revision_state(
                        prior_path_lookup.get(path_id), state, str(decision_at)
                    )
                    if dict(revision) != expected_revision:
                        raise InferenceV2Error("SIDECAR_REVISION_SEMANTICS_MISMATCH")
                record_candidate = dict(path)
                record_digest = record_candidate.pop("path_record_digest", None)
                if record_digest != canonical_digest(record_candidate):
                    raise InferenceV2Error("SIDECAR_PATH_RECORD_DIGEST_MISMATCH")
            if named_count < 2:
                raise InferenceV2Error("SIDECAR_PATH_CARDINALITY_VIOLATION")
            if not set(RESIDUAL_PATH_IDS).issubset(path_ids):
                raise InferenceV2Error("SIDECAR_REQUIRED_RESIDUAL_MISSING")
            residuals = _mapping(
                target.get("residual_nodes"), "SIDECAR_RESIDUAL_MAP_MISSING"
            )
            if residuals.get("reader_union_label") != "OTHER_OR_UNKNOWN":
                raise InferenceV2Error("SIDECAR_RESIDUAL_UNION_INVALID")
            target_candidate = dict(target)
            target_digest = target_candidate.pop("target_digest", None)
            if target_digest != canonical_digest(target_candidate):
                raise InferenceV2Error("SIDECAR_TARGET_DIGEST_MISMATCH")
        symbol_candidate = dict(symbol)
        symbol_digest = symbol_candidate.pop("symbol_review_digest", None)
        if symbol_digest != canonical_digest(symbol_candidate):
            raise InferenceV2Error("SIDECAR_SYMBOL_DIGEST_MISMATCH")
    pit = _mapping(sidecar.get("point_in_time"), "SIDECAR_PIT_MISSING")
    if pit.get("future_evidence_violations") != []:
        raise InferenceV2Error("SIDECAR_PIT_VIOLATION_RECORDED")
    if pit.get("admitted_evidence_count") != evidence_count:
        raise InferenceV2Error("SIDECAR_EVIDENCE_COUNT_MISMATCH")
    return {
        "valid": True,
        "sidecar_digest": supplied_digest,
        "symbol_count": len(symbols),
        "target_count": target_count,
        "evidence_count": evidence_count,
    }
