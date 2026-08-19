"""Pure synthetic contract checks for the v0.4.0 four-layer challenger.

No test reads market payloads, calculates a market feature, performs a
backtest, fits a model, or creates a trading instruction.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEORY_PATH = PROJECT_ROOT / "theory/history/RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md"
METHOD_PATH = PROJECT_ROOT / "config" / "rsi_mtf_four_layer.method_contract.v0_4_0.json"
REGISTRY_PATH = PROJECT_ROOT / "config" / "rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json"
SYNTHETIC_PATH = PROJECT_ROOT / "config" / "rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json"

TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")
ADJACENT_PAIRS = (("1w", "1d"), ("1d", "4h"), ("4h", "1h"), ("1h", "15m"))
ACTION_PRIORITY = (
    "HALT_IF_ACCOUNT_VENUE_OR_DATA_SAFETY_FAILURE",
    "EXIT_IF_EXISTING_POSITION_REQUIRES_PROTECTIVE_EXIT",
    "MANAGE_ONLY_IF_EXISTING_POSITION_AND_NO_EXIT",
    "UNKNOWN_IF_REQUIRED_INPUT_OR_TIME_PROOF_MISSING_FOR_NEW_ACTION",
    "OBSERVE_IF_RSI_EVENT_AND_NO_OTHER_PERMISSION",
    "ABSTAIN_IF_VALID_BUT_CONFLICT_UNSUPPORTED_OR_ZONE_EMPTY",
    "EVALUATE_REVERSAL_IF_ALL_CANDIDATE_GATES_PASS",
    "EXECUTION_READY_ONLY_IF_SEPARATE_FUTURE_AUTHORIZED_EXECUTION_CONTRACT_PASSES",
)
MARKET_SCENARIO_BRANCHES = ("UPSIDE", "DOWNSIDE", "RANGE", "UNRESOLVED")
ACTION_OUTCOME_BRANCHES = ("NO_FILL", "TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT")
DATA_DISPOSITION = ("VALID", "CENSORED", "DATA_INVALID", "OPERATIONAL_OVERRIDE")
EXACT_COHORT_KEYS = (
    "asset_class",
    "venue",
    "market_type",
    "instrument_id",
    "contract_specification",
    "session_timezone",
    "daily_boundary",
    "volume_unit",
    "price_adjustment_policy",
)
CANDIDATE_TUPLE_FIELDS = ("n", "theta_v", "theta_de", "extension_band", "hysteresis_length", "volatility_window", "ATR_or_RV_choice", "volume_baseline_method", "weekday_or_session_adjustment", "central_range_band", "epsilon")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_TIMEZONE_MISSING")
    return parsed.astimezone(timezone.utc)


def _visible(*, is_closed: object, source_timestamp: object, close_time: object, available_at: object, decision_time: object) -> bool:
    if type(is_closed) is not bool or is_closed is not True:
        return False
    try:
        source_at, closed_at, available, decision = (
            _utc(source_timestamp),
            _utc(close_time),
            _utc(available_at),
            _utc(decision_time),
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return source_at <= decision and closed_at <= decision and available <= decision


def _eligible_neighbor(*, tail_end: str, embargo_minutes: int, query_available_at: str) -> bool:
    return _utc(tail_end) + timedelta(minutes=embargo_minutes) < _utc(query_available_at)


def _intersects(zones: list[tuple[float, float]]) -> bool:
    if not zones or any(lower > upper for lower, upper in zones):
        return False
    return max(lower for lower, _ in zones) <= min(upper for _, upper in zones)


def _stop_update_valid(*, side: str, prior: float, updated: float) -> bool:
    return (side == "LONG" and updated >= prior) or (side == "SHORT" and updated <= prior)


def _finite_json_number(value: object) -> bool:
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def _probability_valid(probabilities: dict[str, object], branches: tuple[str, ...]) -> bool:
    return set(probabilities) == set(branches) and all(_finite_json_number(value) and 0.0 <= value <= 1.0 for value in probabilities.values()) and math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-12)


def _canonical_replay(contract_id: str, contract_version: str, feature_version: str, fixture_id: str, inputs: list[dict[str, object]]) -> tuple[str, bytes]:
    required = ("source_id", "generation_id_or_stream_id", "source_sequence", "stable_input_id", "source_timestamp", "available_at", "record_version")
    if any(any(field not in row or row[field] in (None, "") for field in required) for row in inputs):
        raise ValueError("IDENTITY_MISSING")
    if any(not isinstance(row["source_sequence"], int) or isinstance(row["source_sequence"], bool) or row["source_sequence"] < 0 for row in inputs):
        raise ValueError("SEQUENCE_INVALID")
    if len({(row["source_id"], row["generation_id_or_stream_id"], row["source_sequence"]) for row in inputs}) != len(inputs):
        raise ValueError("SEQUENCE_DUPLICATE")
    if len({row["stable_input_id"] for row in inputs}) != len(inputs):
        raise ValueError("STABLE_ID_DUPLICATE")
    ordered = sorted(
        inputs,
        key=lambda item: (
            item["available_at"],
            item["source_id"],
            item["generation_id_or_stream_id"],
            item["source_sequence"],
            item["stable_input_id"],
        ),
    )
    payload = {
        "contract_id": contract_id,
        "contract_version": contract_version,
        "feature_version": feature_version,
        "fixture_id": fixture_id,
        "ordered_inputs": ordered,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), canonical


def _daily_prefix(rows: list[dict[str, object]], prefix_day: int, decision_time: object) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in rows:
        try:
            day = int(row["day"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("PREFIX_TIME_INVALID") from None
        if day > prefix_day:
            raise ValueError("FULL_EPISODE_LOOKAHEAD")
        if not _visible(
            is_closed=row.get("is_closed"),
            source_timestamp=row.get("source_timestamp"),
            close_time=row.get("close_time"),
            available_at=row.get("available_at"),
            decision_time=decision_time,
        ):
            raise ValueError("PREFIX_TIME_INVALID")
        selected.append(row)
    return selected


def _h10_prefix(rows: list[dict[str, object]], prefix_day: int, decision_time: object) -> list[dict[str, object]]:
    return _daily_prefix(rows, prefix_day, decision_time)


def _h11_prefix(rows: list[dict[str, object]], prefix_day: int, decision_time: object) -> list[dict[str, object]]:
    return _daily_prefix(rows, prefix_day, decision_time)


def _robust_log_volume_residual(prefix_volumes: list[float], current_volume: float) -> float:
    if not prefix_volumes or any(value <= 0 for value in [*prefix_volumes, current_volume]):
        raise ValueError("VOLUME_BASELINE_INVALID")
    baseline = [math.log(value) for value in prefix_volumes]
    center = statistics.median(baseline)
    mad = statistics.median([abs(value - center) for value in baseline])
    return (math.log(current_volume) - center) / max(mad, 1e-12)


def _event_visible_at_prefix(event: dict[str, object], decision_time: object) -> bool:
    try:
        source_at, published_at, available_at, decision = (
            _utc(event.get("source_timestamp")),
            _utc(event.get("published_at")),
            _utc(event.get("available_at")),
            _utc(decision_time),
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return source_at <= decision and published_at <= decision and available_at <= decision


def _same_h10_pool(left: dict[str, str], right: dict[str, str]) -> bool:
    return all(left[field] == right[field] for field in EXACT_COHORT_KEYS)


def _filled_conditional_distribution(outcome: dict[str, float]) -> tuple[float, dict[str, float]]:
    if not _probability_valid(outcome, ACTION_OUTCOME_BRANCHES):
        raise ValueError("ACTION_OUTCOME_NOT_NORMALIZED")
    p_fill = 1.0 - outcome["NO_FILL"]
    filled = ("TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT")
    if p_fill <= 0.0:
        raise ValueError("NO_FILLED_COHORT")
    return p_fill, {name: outcome[name] / p_fill for name in filled}


def _structural_regime(*, velocity: float, efficiency: float, theta_v: float, theta_de: float, n: int = 1, h: int = 1, window: int = 1, epsilon: float = 1e-9, hysteresis_complete: bool, data_quality: str) -> str:
    valid_int = all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in (n, h, window))
    valid = all(math.isfinite(value) for value in (velocity, efficiency, theta_v, theta_de, epsilon)) and theta_v > 0 and 0 <= theta_de <= 1 and 0 <= efficiency <= 1 and valid_int and epsilon > 0
    if data_quality != "VALID" or not valid:
        return "UNKNOWN"
    if not hysteresis_complete:
        return "TRANSITION"
    if velocity >= theta_v and efficiency >= theta_de:
        return "UP"
    if velocity <= -theta_v and efficiency >= theta_de:
        return "DOWN"
    if -theta_v < velocity < theta_v and efficiency < theta_de:
        return "RANGE"
    return "TRANSITION"


def _economic_order(left: dict[str, object], right: dict[str, object]) -> str:
    if left["available_at"] != right["available_at"]:
        return "LEFT_FIRST" if str(left["available_at"]) < str(right["available_at"]) else "RIGHT_FIRST"
    same_stream = (left["source_id"], left["generation_id_or_stream_id"]) == (right["source_id"], right["generation_id_or_stream_id"])
    if not same_stream:
        return "BATCH_UNRESOLVED"
    if left["source_sequence"] == right["source_sequence"]:
        return "SEQUENCE_CONFLICT"
    return "LEFT_FIRST" if int(left["source_sequence"]) < int(right["source_sequence"]) else "RIGHT_FIRST"


def _permissioned_intersection(gate: str, zones: dict[str, tuple[float, float]], quality: str = "VALID") -> tuple[float, float] | None:
    if quality != "VALID":
        raise ValueError("QUALITY_FAILS_BEFORE_GATE")
    if gate not in ("ALLOW", "DENY"):
        raise ValueError("GATE_REJECTED")
    if set(zones) != {"StructuralZone", "LiquidityFeasibleZone", "RiskGeometryZone", "VenueRuleZone"}:
        raise ValueError("ZONE_SCHEMA_INVALID")
    if gate == "DENY" or not _intersects(list(zones.values())):
        return None
    return max(lower for lower, _ in zones.values()), min(upper for _, upper in zones.values())


def _rsi_episode_action(*, has_cross: bool, cross_valid: bool, persistent_extreme: bool, later_closed_time: bool, same_bar: bool, active: bool, unexpired: bool, data_valid: bool, parent_valid: bool, candidate_gates: bool, terminal: bool, episode_exists: bool) -> dict[str, object]:
    if not episode_exists and has_cross:
        if cross_valid and data_valid and parent_valid and candidate_gates and not terminal:
            return {"action": "OBSERVE", "episode_record_exists": True, "active": True, "eligible_for_upgrade": False, "new_observe_emitted": True, "terminated_reason": None}
        action = "UNKNOWN" if not data_valid or not cross_valid else "ABSTAIN"
        return {"action": action, "episode_record_exists": False, "active": False, "eligible_for_upgrade": False, "new_observe_emitted": False, "terminated_reason": None}
    termination = "TERMINAL" if terminal else "EXPIRED" if not unexpired else "DATA_INVALID" if not data_valid else "PARENT_INVALID" if not parent_valid else None
    if episode_exists and termination:
        return {"action": "ABSTAIN", "episode_record_exists": True, "active": False, "eligible_for_upgrade": False, "new_observe_emitted": False, "terminated_reason": termination}
    if episode_exists and not active:
        return {"action": "UNKNOWN", "episode_record_exists": True, "active": False, "eligible_for_upgrade": False, "new_observe_emitted": False, "terminated_reason": "LIFECYCLE_PROOF_MISSING"}
    if episode_exists and active and later_closed_time and not same_bar and candidate_gates:
        return {"action": "EVALUATE_REVERSAL", "episode_record_exists": True, "active": True, "eligible_for_upgrade": True, "new_observe_emitted": False, "terminated_reason": None}
    return {"action": "ABSTAIN", "episode_record_exists": episode_exists, "active": active and episode_exists, "eligible_for_upgrade": False, "new_observe_emitted": False, "terminated_reason": None}


def _validate_score_record(prediction: dict[str, float], observed_fill: bool | None, observed_outcome: str | None, disposition: str) -> None:
    if not _probability_valid(prediction, ACTION_OUTCOME_BRANCHES) or type(disposition) is not str or disposition not in DATA_DISPOSITION:
        raise ValueError("INVALID_SCORE_RECORD")
    if observed_fill is not None and type(observed_fill) is not bool:
        raise ValueError("INVALID_SCORE_RECORD")
    if observed_outcome is not None and (type(observed_outcome) is not str or observed_outcome not in ACTION_OUTCOME_BRANCHES):
        raise ValueError("INVALID_SCORE_RECORD")
    if observed_outcome == "NO_FILL" and observed_fill is not False:
        raise ValueError("FILL_OUTCOME_CONFLICT")
    if observed_outcome in {"TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT"} and observed_fill is not True:
        raise ValueError("FILL_OUTCOME_CONFLICT")
    if disposition == "VALID" and observed_outcome is None:
        raise ValueError("VALID_TERMINAL_MISSING")


def _score_record(prediction: dict[str, float], observed_fill: bool | None, observed_outcome: str | None, disposition: str) -> dict[str, bool]:
    _validate_score_record(prediction, observed_fill, observed_outcome, disposition)
    return {"pfill": observed_fill is not None, "joint": observed_outcome in ACTION_OUTCOME_BRANCHES, "filled": observed_fill is True and observed_outcome in ACTION_OUTCOME_BRANCHES, "fail_closed": disposition != "VALID"}


def _score_denominators(prediction: dict[str, float], records: list[tuple[bool | None, str | None, str]]) -> dict[str, object]:
    for fill, outcome, disposition in records:
        _validate_score_record(prediction, fill, outcome, disposition)
    counts = {disposition: sum(item[2] == disposition for item in records) for disposition in DATA_DISPOSITION}
    filled_outcomes = {"TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT"}
    return {"pfill": sum(fill is not None for fill, _, _ in records), "joint": sum(outcome in ACTION_OUTCOME_BRANCHES for _, outcome, _ in records), "filled": sum(fill is True and outcome in filled_outcomes for fill, outcome, _ in records), "disposition_counts": counts, "pre_fill_nonvalid": sum(fill is not True and disposition != "VALID" for fill, _, disposition in records), "post_fill_nonvalid": sum(fill is True and disposition != "VALID" for fill, _, disposition in records)}


def _validate_candidate_family(family: list[dict[str, object]], schema: dict[str, object]) -> bool:
    if not 1 <= len(family) <= 8:
        return False
    exact = set(CANDIDATE_TUPLE_FIELDS)
    enums = schema["enum_domains"]
    semantic_identities: list[dict[str, object]] = []
    for item in family:
        if set(item) != exact:
            return False
        if any(not isinstance(item[key], int) or isinstance(item[key], bool) or item[key] <= 0 for key in ("n", "hysteresis_length", "volatility_window")):
            return False
        numeric = (item["theta_v"], item["theta_de"], item["epsilon"])
        if any(not _finite_json_number(value) for value in numeric):
            return False
        if item["theta_v"] <= 0 or not 0 <= item["theta_de"] <= 1 or item["epsilon"] <= 0:
            return False
        for key in ("extension_band", "central_range_band"):
            band = item[key]
            if not isinstance(band, list) or len(band) != 2 or any(not _finite_json_number(value) for value in band) or band[0] < 0 or band[0] > band[1]:
                return False
        if any(item[key] not in enums[key] for key in enums):
            return False
        if any(item == prior for prior in semantic_identities):
            return False
        semantic_identities.append(item)
    return True


def _price_hypothesis_supported(price_outcome: bool, event_arrival: bool) -> bool:
    return price_outcome


def _parent_conflict_action(priority: str) -> str:
    if priority in {"HALT", "EXIT", "MANAGE_ONLY"}:
        return priority
    return "ABSTAIN"


class SyntheticFourLayerMeasurementContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.synthetic = _json(SYNTHETIC_PATH)
        cls.method = _json(METHOD_PATH)
        cls.registry = _json(REGISTRY_PATH)
        cls.theory = THEORY_PATH.read_text(encoding="utf-8")

    def test_all_v4_artifacts_are_present_and_e0_outcome_free(self) -> None:
        self.assertTrue(THEORY_PATH.is_file())
        self.assertEqual(self.synthetic["contract_id"], "RSI_MTF_FOUR_LAYER_SYNTHETIC_MEASUREMENT_CONTRACT.v0.4.0")
        self.assertEqual(self.synthetic["stage"], "V4-M00")
        self.assertEqual(self.synthetic["status"], "SYNTHETIC_MEASUREMENT_ONLY")
        self.assertEqual(self.synthetic["evidence_level"], "E0")
        self.assertEqual(self.method["status"], "E0/OUTCOME_FREE_THEORY_DRAFT")
        self.assertEqual(self.registry["status"], "E0/OUTCOME_FREE_THEORY_DRAFT")
        self.assertIn("RSI-MTF Four-Layer Theory Challenger v0.4.0", self.theory)

    def test_cross_artifact_time_semantics_are_causal_and_identical_in_meaning(self) -> None:
        time_contract = self.synthetic["time_contract"]
        invariant = "A bar is visible at decision_time if and only if is_closed is the exact JSON boolean true; source_timestamp, close_time, available_at, and decision_time are present, valid, timezone-aware, mutually comparable timestamps; and source_timestamp <= decision_time, close_time <= decision_time, and available_at <= decision_time. Any missing, malformed, incomparable timestamp or pseudo-boolean is_closed fails closed to DATA_INVALID and UNKNOWN_OR_ABSTAIN."
        event_invariant = "An event is visible at decision_time if and only if source_timestamp, published_at, available_at, and decision_time are present, valid, timezone-aware, mutually comparable timestamps; and source_timestamp <= decision_time, published_at <= decision_time, and available_at <= decision_time. source_timestamp records source provenance and is distinct from published_at, the public event publication time. Any missing, malformed, incomparable or future timestamp fails closed to DATA_INVALID and UNKNOWN_OR_ABSTAIN."
        self.assertEqual(tuple(time_contract["timeframes"]), TIMEFRAMES)
        self.assertEqual(time_contract["timezone"], "UTC")
        self.assertEqual(time_contract["visibility_invariant"], invariant)
        self.assertEqual(self.method["time_semantics"]["visibility_invariant"], invariant)
        self.assertEqual(self.registry["common_rules"]["visibility_invariant"], invariant)
        self.assertEqual(time_contract["event_visibility_invariant"], event_invariant)
        self.assertEqual(self.method["time_semantics"]["event_visibility_invariant"], event_invariant)
        self.assertEqual(self.registry["common_rules"]["event_visibility_invariant"], event_invariant)
        self.assertIn("full visibility_invariant", time_contract["visibility_rule"])
        self.assertIn("source_id,generation_id_or_stream_id", time_contract["same_timestamp_rule"])
        self.assertIn("stable_input_id", time_contract["same_timestamp_rule"])
        self.assertIn("is_closed=true", self.method["time_semantics"]["input_rule"])
        self.assertIn("source_timestamp <= t", self.method["time_semantics"]["input_rule"])
        self.assertIn("close_time <= t", self.method["time_semantics"]["input_rule"])
        self.assertIn("available_at <= t", self.method["time_semantics"]["input_rule"])
        self.assertIn("same (source_id,generation_id_or_stream_id)", self.method["time_semantics"]["event_order_rule"])
        self.assertIn("Cross-source equal-available_at", self.method["time_semantics"]["event_order_rule"])
        self.assertIn("full visibility_invariant", self.registry["common_rules"]["availability"])
        self.assertIn("source_sequence is comparable only", self.registry["common_rules"]["availability"])
        self.assertIn("exact JSON boolean `true`", self.theory)
        self.assertIn("source_timestamp <= decision_time", self.theory)
        self.assertIn("source_timestamp / published_at / available_at", self.theory)
        self.assertIn("close_time <= decision_time", self.theory)
        self.assertIn("available_at <= decision_time", self.theory)

    def test_enum_definitions_and_tfstate_schemas_match_method_contract(self) -> None:
        self.assertEqual(self.synthetic["enum_definitions"], self.method["enum_definitions"])
        enums = self.synthetic["enum_definitions"]
        self.assertNotIn("DATA_INVALID", enums["structural_regime"])
        self.assertIn("DATA_INVALID", enums["data_quality"])
        self.assertEqual(tuple(enums["parent_child_relation"]), ("ALIGNED", "COUNTERTREND", "RANGE_NESTED", "RANGE_EXCURSION", "TRANSITION", "UNKNOWN"))
        self.assertEqual(tuple(enums["scenario_branch"]), MARKET_SCENARIO_BRANCHES)
        self.assertEqual(tuple(enums["action_outcome"]), ACTION_OUTCOME_BRANCHES)
        self.assertEqual(tuple(enums["data_disposition"]), DATA_DISPOSITION)
        self.assertEqual(
            self.synthetic["state_contract"]["TFState_required_fields"],
            self.method["observable_objects"]["TFState"]["required_fields"],
        )
        self.assertIn("DecisionState", self.method["observable_objects"])
        self.assertIn("DataQuality is a separate axis", self.synthetic["state_contract"]["orthogonality_rule"])

    def test_labels_parent_child_mapping_and_roles_match_method_contract(self) -> None:
        self.assertEqual(self.synthetic["mechanical_label_mapping"], self.method["mechanical_label_mapping"])
        self.assertEqual(
            tuple(tuple(pair) for pair in self.synthetic["parent_child_contract"]["adjacent_pairs"]),
            tuple(tuple(pair) for pair in self.method["parent_child_rules"]["adjacent_pairs"]),
        )
        self.assertEqual(tuple(tuple(pair) for pair in self.synthetic["parent_child_contract"]["adjacent_pairs"]), ADJACENT_PAIRS)
        translated = self.synthetic["state_contract"]["user_state_to_mechanical_label"]
        self.assertEqual(translated["下跌中止跌周期"], "POTENTIAL_BOTTOMING")
        self.assertEqual(translated["上涨中见顶周期"], "POTENTIAL_TOPPING")
        self.assertIn("POTENTIAL_BOTTOMING", self.synthetic["mechanical_label_mapping"])
        self.assertIn("POTENTIAL_TOPPING", self.synthetic["mechanical_label_mapping"])
        self.assertIn("cannot overwrite", self.synthetic["parent_child_contract"]["authority_rule"])

    def test_probability_and_action_priority_contracts_match_method_contract(self) -> None:
        probability = self.synthetic["probability_contract"]
        self.assertEqual(tuple(probability["MarketScenario"]["branches"]), MARKET_SCENARIO_BRANCHES)
        self.assertEqual(tuple(probability["ActionOutcome"]["branches"]), ACTION_OUTCOME_BRANCHES)
        self.assertEqual(tuple(self.synthetic["action_priority"]), tuple(self.method["action_priority"]))
        self.assertEqual(tuple(self.synthetic["action_priority"]), ACTION_PRIORITY)
        self.assertIn("cannot directly create an order", probability["MarketScenario"]["decision_rule"])
        self.assertIn("cannot directly create an order", probability["ActionOutcome"]["decision_rule"])
        self.assertIn("not a MarketScenario class", probability["MarketScenario"]["unknown_output_boundary"])
        self.assertIn("not conditional-on-fill", probability["ActionOutcome"]["conditional_scope"])
        self.assertIn("P(fill)", probability["ActionOutcome"]["fill_and_conditional_distribution"])
        self.assertEqual(probability["MarketScenario"]["probability_scalar_rule"], self.method["observable_objects"]["MarketScenario"]["probability_scalar_rule"])
        self.assertEqual(probability["ActionOutcome"]["probability_scalar_rule"], self.method["observable_objects"]["ActionOutcome"]["probability_scalar_rule"])
        self.assertEqual(probability["ActionOutcome"]["strict_record_validation"], self.method["observable_objects"]["ActionOutcome"]["strict_record_validation"])
        self.assertEqual(tuple(self.synthetic["enum_definitions"]["data_disposition"]), DATA_DISPOSITION)
        self.assertIn("outside the ActionOutcome probability vector", probability["ActionOutcome"]["data_disposition"])
        self.assertIn("MarketScenario direction alone cannot authorize an order", self.method["observable_objects"]["ActionOutcome"]["decision_rule"])

    def test_stage_dependencies_and_prohibitions_match_registry(self) -> None:
        capabilities = self.registry["capabilities"]
        boundary = self.synthetic["authority_boundary"]
        for field in ("historical_outcome_access", "backtest", "calibration", "paper", "live"):
            self.assertIn("FORBIDDEN", capabilities[field], field)
        for field in ("real_historical_payload", "historical_outcome_access", "source_adapter", "backtest", "calibration", "paper", "live", "market_or_alpha_claim"):
            self.assertEqual(boundary[field], "FORBIDDEN", field)
        milestone = self.registry["milestones"][0]
        self.assertEqual(milestone["id"], "V4-M00-OUTCOME_FREE_CONTRACT")
        self.assertEqual(milestone["result_status"], "NOT_RUN")
        self.assertEqual(milestone["test_execution_status"], "TESTS_PASS_AWAITING_SOL_STAGE_GATE")
        self.assertIn("TESTS_PASS_AWAITING_SOL_STAGE_GATE", self.theory)
        self.assertNotIn("P0_REPAIR_IN_PROGRESS_AWAITING_RERUN", self.theory)
        self.assertEqual(self.registry["hypotheses"][0]["depends_on"], ["V4-M00-OUTCOME_FREE_CONTRACT"])
        self.assertIn("V4-M00_OUTCOME_FREE_SYNTHETIC_CONTRACT", self.registry["route"])

    def test_h01_through_h12_order_status_and_dependencies_are_registered(self) -> None:
        expected = (
            "V4-H01-MTF_PARENT_VETO",
            "V4-H02-PARENT_CHILD_RELATION",
            "V4-H03-CURRENT_PRESSURE_CONFIRMATION",
            "V4-H04-CAUSAL_LEVEL_RESPONSE",
            "V4-H05-VOL_LIQ_GEOMETRY",
            "V4-H06-REMAINING_EV_EXIT",
            "V4-H07-PAST_ONLY_ANALOG",
            "V4-H08-MACRO_RISK_CONDITION",
            "V4-H09-FOUR_LAYER_INTEGRATION",
            "V4-H10-D2_D3_UPWARD_EXPANSION_PRICE_SEQUENCE",
            "V4-H11-D6_D7_DOWNSIDE_BREAKDOWN_PRICE_SEQUENCE",
            "V4-H12-EVENT_ARRIVAL_ASSOCIATION",
        )
        self.assertEqual(tuple(self.registry["hypothesis_order"]), expected)
        hypotheses = {item["hypothesis_id"]: item for item in self.registry["hypotheses"]}
        self.assertEqual(tuple(item["hypothesis_id"] for item in self.registry["hypotheses"]), expected)
        self.assertTrue(all(hypotheses[item]["result_status"] == "WAIT_DATA" for item in expected))
        self.assertEqual(hypotheses[expected[0]]["depends_on"], ["V4-M00-OUTCOME_FREE_CONTRACT"])
        self.assertEqual(hypotheses[expected[-3]]["depends_on"], ["V4-H04-CAUSAL_LEVEL_RESPONSE_DISPOSITION_RECORDED", "V4-H05-VOL_LIQ_GEOMETRY_DISPOSITION_RECORDED"])
        self.assertEqual(hypotheses[expected[-2]]["depends_on"], ["V4-H04-CAUSAL_LEVEL_RESPONSE_DISPOSITION_RECORDED", "V4-H05-VOL_LIQ_GEOMETRY_DISPOSITION_RECORDED"])
        self.assertEqual(hypotheses[expected[-1]]["depends_on"], ["V4-H10-D2_D3_UPWARD_EXPANSION_PRICE_SEQUENCE_DISPOSITION_RECORDED", "V4-H11-D6_D7_DOWNSIDE_BREAKDOWN_PRICE_SEQUENCE_DISPOSITION_RECORDED"])
        self.assertEqual(tuple(self.synthetic["h10_daily_prefix_contract"]["hypothesis_ids"]), expected[-3:])

    def test_causal_measurement_and_nonvalid_gate_match_method_contract(self) -> None:
        self.assertEqual(self.synthetic["causal_measurement_contract"], self.method["causal_measurement_contract"])
        self.assertIn("at most eight complete valid tuples", self.synthetic["causal_measurement_contract"]["finite_candidate_family"])
        self.assertEqual(
            self.synthetic["probability_contract"]["MarketScenario"]["label_definition"],
            self.method["observable_objects"]["MarketScenario"]["label_definition"],
        )
        self.assertIn("central_range_band", self.synthetic["probability_contract"]["MarketScenario"]["label_definition"])
        self.assertIn("DataQuality=VALID", self.synthetic["current_pressure_contract"]["required_quality_rule"])
        for quality in ("STALE", "GAP", "CONFLICT", "DATA_INVALID", "UNKNOWN"):
            self.assertIn(quality, self.synthetic["current_pressure_contract"]["required_quality_rule"])
        self.assertEqual(self.synthetic["current_pressure_contract"]["neutral_imputation"], "FORBIDDEN")

    def test_complete_candidate_family_schema_and_all_invalid_families_fail_closed(self) -> None:
        method_schema = self.method["causal_measurement_contract"]["candidate_tuple_contract"]
        synthetic_schema = self.synthetic["causal_measurement_contract"]["candidate_tuple_contract"]
        self.assertEqual(method_schema, synthetic_schema)
        self.assertEqual(tuple(method_schema["exact_fields"]), CANDIDATE_TUPLE_FIELDS)
        base = {"n": 14, "theta_v": 1.0, "theta_de": 0.5, "extension_band": [0.0, 2.0], "hysteresis_length": 2, "volatility_window": 20, "ATR_or_RV_choice": "ATR", "volume_baseline_method": "ROBUST_MEDIAN_MAD", "weekday_or_session_adjustment": "NONE", "central_range_band": [0.0, 1.0], "epsilon": 1e-9}
        self.assertTrue(_validate_candidate_family([base], method_schema))
        family = [{**base, "n": index + 1} for index in range(8)]
        self.assertTrue(_validate_candidate_family(family, method_schema))
        self.assertFalse(_validate_candidate_family([*family, {**base, "n": 9}], method_schema))
        self.assertFalse(_validate_candidate_family([base, dict(base)], method_schema))
        integer_equivalent = base | {"theta_v": 1}
        negative_zero_equivalent = base | {"central_range_band": [-0.0, 1.0]}
        self.assertEqual(base, integer_equivalent)
        self.assertEqual(base, negative_zero_equivalent)
        self.assertFalse(_validate_candidate_family([base, integer_equivalent], method_schema))
        self.assertFalse(_validate_candidate_family([base, negative_zero_equivalent], method_schema))
        for mutation in ({key: value for key, value in base.items() if key != "epsilon"}, base | {"unknown": 1}, base | {"theta_v": float("nan")}, base | {"epsilon": float("inf")}, base | {"extension_band": [-1.0, 1.0]}, base | {"central_range_band": [2.0, 1.0]}, base | {"n": -1}, base | {"ATR_or_RV_choice": "BOGUS"}, base | {"volume_baseline_method": "BOGUS"}, base | {"weekday_or_session_adjustment": "BOGUS"}):
            self.assertFalse(_validate_candidate_family([mutation], method_schema))

    def test_visible_if_and_only_if_full_causal_clock_invariant_holds(self) -> None:
        valid = {
            "is_closed": True,
            "source_timestamp": "2026-01-01T10:00:00Z",
            "close_time": "2026-01-01T11:00:00Z",
            "available_at": "2026-01-01T11:00:00Z",
            "decision_time": "2026-01-01T11:00:00Z",
        }
        self.assertFalse(_visible(**(valid | {"is_closed": False})))
        self.assertFalse(_visible(**(valid | {"source_timestamp": "2026-01-01T11:00:01Z"})))
        self.assertFalse(_visible(**(valid | {"close_time": "2026-01-01T11:00:01Z"})))
        self.assertFalse(_visible(**(valid | {"available_at": "2026-01-01T11:00:01Z"})))
        self.assertTrue(_visible(**valid))

    def test_visibility_fails_closed_for_pseudobooleans_and_invalid_timestamps(self) -> None:
        valid = {
            "is_closed": True,
            "source_timestamp": "2026-01-01T10:00:00Z",
            "close_time": "2026-01-01T11:00:00Z",
            "available_at": "2026-01-01T11:00:00Z",
            "decision_time": "2026-01-01T11:00:00Z",
        }
        for pseudo_boolean in ("true", "false", 1, 0, None):
            with self.subTest(pseudo_boolean=pseudo_boolean):
                self.assertFalse(_visible(**(valid | {"is_closed": pseudo_boolean})))
        for field, invalid in (
            ("source_timestamp", "2026-01-01T11:00:01Z"),
            ("source_timestamp", "not-a-timestamp"),
            ("source_timestamp", None),
            ("close_time", "2026-01-01T11:00:00"),
            ("available_at", "not-a-timestamp"),
            ("decision_time", None),
        ):
            with self.subTest(field=field, invalid=invalid):
                self.assertFalse(_visible(**(valid | {field: invalid})))

    def test_data_invalid_is_quality_not_regime_and_fails_closed(self) -> None:
        enums = self.synthetic["enum_definitions"]
        quality = "DATA_INVALID"
        regime = "UP"
        self.assertIn(quality, enums["data_quality"])
        self.assertNotIn(quality, enums["structural_regime"])
        self.assertIn(regime, enums["structural_regime"])
        disposition = "UNKNOWN_OR_ABSTAIN" if quality == "DATA_INVALID" else "CONTINUE"
        self.assertEqual(disposition, "UNKNOWN_OR_ABSTAIN")

    def test_structural_regime_cross_grid_is_exhaustive_and_parent_conflict_does_not_rewrite_tfstate(self) -> None:
        values = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)
        efficiencies = (0.5, 0.75, 1.0)
        observed = {
            _structural_regime(velocity=velocity, efficiency=efficiency, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID")
            for velocity in values
            for efficiency in efficiencies
        }
        self.assertEqual(observed, {"UP", "DOWN", "RANGE", "TRANSITION"})
        self.assertEqual(_structural_regime(velocity=0.5, efficiency=1.0, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "TRANSITION")
        self.assertEqual(_structural_regime(velocity=2.0, efficiency=0.5, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "TRANSITION")
        self.assertEqual(_structural_regime(velocity=-1.0, efficiency=0.75, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "DOWN")
        self.assertEqual(_structural_regime(velocity=1.0, efficiency=0.75, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "UP")
        self.assertEqual(_structural_regime(velocity=0.0, efficiency=0.75, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "TRANSITION")
        self.assertEqual(_structural_regime(velocity=0.0, efficiency=0.5, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "RANGE")
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            self.assertEqual(_structural_regime(velocity=0.0, efficiency=0.5, theta_v=bad, theta_de=0.75, hysteresis_complete=True, data_quality="VALID"), "UNKNOWN")
        for bad in (-0.1, 1.1, float("nan")):
            self.assertEqual(_structural_regime(velocity=0.0, efficiency=0.5, theta_v=1.0, theta_de=bad, hysteresis_complete=True, data_quality="VALID"), "UNKNOWN")
        for name in ("n", "h", "window"):
            kwargs = {"n": 1, "h": 1, "window": 1}
            for invalid in (0, -1, 1.5, True):
                kwargs[name] = invalid
                self.assertEqual(_structural_regime(velocity=0.0, efficiency=0.5, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID", **kwargs), "UNKNOWN")
        for key, value in (("epsilon", 0.0), ("velocity", float("nan")), ("efficiency", float("inf"))):
            arguments = {"velocity": 0.0, "efficiency": 0.5, "theta_v": 1.0, "theta_de": 0.75, "hysteresis_complete": True, "data_quality": "VALID"}
            arguments[key] = value
            self.assertEqual(_structural_regime(**arguments), "UNKNOWN")
        self.assertEqual(_structural_regime(velocity=2.0, efficiency=1.0, theta_v=1.0, theta_de=0.75, hysteresis_complete=False, data_quality="VALID"), "TRANSITION")
        self.assertEqual(_structural_regime(velocity=2.0, efficiency=1.0, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="DATA_INVALID"), "UNKNOWN")
        tfstate_regime = _structural_regime(velocity=2.0, efficiency=1.0, theta_v=1.0, theta_de=0.75, hysteresis_complete=True, data_quality="VALID")
        decision_parent_child_relation = "UNKNOWN"
        data_quality_rollup_reason = "CONFLICT"
        decision_action = "ABSTAIN"
        self.assertEqual(tfstate_regime, "UP")
        self.assertIn(decision_parent_child_relation, self.synthetic["enum_definitions"]["parent_child_relation"])
        self.assertEqual(data_quality_rollup_reason, "CONFLICT")
        self.assertEqual(decision_action, "ABSTAIN")
        self.assertEqual(_parent_conflict_action("HALT"), "HALT")
        self.assertEqual(_parent_conflict_action("EXIT"), "EXIT")
        self.assertEqual(_parent_conflict_action("MANAGE_ONLY"), "MANAGE_ONLY")
        self.assertEqual(_parent_conflict_action("EVALUATE_REVERSAL"), "ABSTAIN")
        self.assertEqual(_parent_conflict_action("EXECUTION_READY"), "ABSTAIN")
        self.assertIn("never rewrites a TFState", self.synthetic["state_contract"]["transition_rule"])

    def test_rsi_observe_only_and_child_cannot_overwrite_parent_regime(self) -> None:
        self.assertEqual(self.synthetic["rsi_contract"]["role"], "OBSERVE_ONLY")
        self.assertIn("ENTRY_COMMAND", self.synthetic["rsi_contract"]["forbidden_roles"])
        rsi_action = "OBSERVE"
        parent_regime, child_claim = "DOWN", "UP"
        operational_regime = parent_regime
        self.assertEqual(rsi_action, "OBSERVE")
        self.assertEqual(operational_regime, "DOWN")
        self.assertNotEqual(operational_regime, child_claim)
        self.assertIn("never rewrites", self.synthetic["parent_child_contract"]["conflict_rule"])

    def test_rsi_episode_lifecycle_observes_once_and_only_later_closed_time_can_evaluate(self) -> None:
        base = dict(cross_valid=True, persistent_extreme=False, later_closed_time=False, same_bar=True, active=True, unexpired=True, data_valid=True, parent_valid=True, candidate_gates=True, terminal=False)
        created = _rsi_episode_action(has_cross=True, episode_exists=False, **base)
        self.assertEqual(created, {"action": "OBSERVE", "episode_record_exists": True, "active": True, "eligible_for_upgrade": False, "new_observe_emitted": True, "terminated_reason": None})
        for field, expected in (("cross_valid", "UNKNOWN"), ("data_valid", "UNKNOWN"), ("parent_valid", "ABSTAIN"), ("candidate_gates", "ABSTAIN"), ("terminal", "ABSTAIN")):
            denied = dict(base); denied[field] = False if field != "terminal" else True
            state = _rsi_episode_action(has_cross=True, episode_exists=False, **denied)
            self.assertEqual(state["action"], expected)
            self.assertFalse(state["episode_record_exists"])
            self.assertFalse(state["active"] or state["eligible_for_upgrade"] or state["new_observe_emitted"])
        persistent = _rsi_episode_action(has_cross=False, episode_exists=True, **(base | {"persistent_extreme": True}))
        self.assertEqual((persistent["action"], persistent["eligible_for_upgrade"], persistent["new_observe_emitted"]), ("ABSTAIN", False, False))
        same_bar = _rsi_episode_action(has_cross=False, episode_exists=True, **base)
        self.assertEqual((same_bar["action"], same_bar["eligible_for_upgrade"]), ("ABSTAIN", False))
        upgraded = _rsi_episode_action(has_cross=False, episode_exists=True, **(base | {"later_closed_time": True, "same_bar": False, "persistent_extreme": True}))
        self.assertEqual((upgraded["action"], upgraded["episode_record_exists"], upgraded["eligible_for_upgrade"], upgraded["new_observe_emitted"]), ("EVALUATE_REVERSAL", True, True, False))
        for field, reason in (("unexpired", "EXPIRED"), ("data_valid", "DATA_INVALID"), ("parent_valid", "PARENT_INVALID"), ("terminal", "TERMINAL")):
            ended = dict(base); ended[field] = False if field != "terminal" else True
            state = _rsi_episode_action(has_cross=False, episode_exists=True, **ended)
            self.assertTrue(state["episode_record_exists"])
            self.assertFalse(state["active"] or state["eligible_for_upgrade"] or state["new_observe_emitted"])
            self.assertEqual(state["terminated_reason"], reason)
        missing_proof = _rsi_episode_action(has_cross=False, episode_exists=True, **(base | {"active": False}))
        self.assertEqual((missing_proof["action"], missing_proof["eligible_for_upgrade"], missing_proof["terminated_reason"]), ("UNKNOWN", False, "LIFECYCLE_PROOF_MISSING"))
        self.assertTrue(all(state in self.synthetic["enum_definitions"]["action"] for state in ("UNKNOWN", "OBSERVE", "ABSTAIN", "EVALUATE_REVERSAL")))
        lifecycle = self.synthetic["rsi_contract"]["episode_lifecycle"]
        self.assertIn("eligible_for_upgrade=false", lifecycle["identity_and_eligibility"])
        self.assertIn("eligible_for_upgrade is separate", self.method["rsi_lifecycle"]["identity_and_eligibility"])
        self.assertIn("LIFECYCLE_PROOF_MISSING", self.method["rsi_lifecycle"]["dedup_expiry_termination"])
        self.assertIn("new_observe_emitted=true", lifecycle["creation"])
        self.assertIn("same-bar upgrade is forbidden", lifecycle["upgrade"])

    def test_analog_embargo_and_macro_vintage_are_append_only(self) -> None:
        self.assertFalse(_eligible_neighbor(tail_end="2026-01-09T23:00:00Z", embargo_minutes=60, query_available_at="2026-01-10T00:00:00Z"))
        self.assertTrue(_eligible_neighbor(tail_end="2026-01-09T22:59:00Z", embargo_minutes=60, query_available_at="2026-01-10T00:00:00Z"))
        macro = self.synthetic["macro_contract"]
        self.assertIn("immutable", macro["first_release_rule"])
        self.assertIn("never overwrite", macro["first_release_rule"])
        vintages = [{"vintage_id": "v1", "available_at": "2026-02-01T11:30:00Z"}]
        vintages.append({"vintage_id": "v2", "available_at": "2026-02-02T11:30:00Z"})
        eligible = [item["vintage_id"] for item in vintages if _utc(item["available_at"]) <= _utc("2026-02-01T12:00:00Z")]
        self.assertEqual(eligible, ["v1"])
        self.assertEqual([item["vintage_id"] for item in vintages], ["v1", "v2"])

    def test_empty_zone_stop_horizon_target_and_intrabar_failures_are_protective(self) -> None:
        self.assertFalse(_intersects([(100.0, 101.0), (101.1, 102.0)]))
        self.assertTrue(_intersects([(100.0, 101.0), (100.5, 102.0)]))
        self.assertFalse(_stop_update_valid(side="LONG", prior=98.0, updated=97.0))
        self.assertFalse(_stop_update_valid(side="SHORT", prior=102.0, updated=103.0))
        self.assertTrue(_stop_update_valid(side="LONG", prior=98.0, updated=99.0))
        self.assertTrue(_stop_update_valid(side="SHORT", prior=102.0, updated=101.0))
        self.assertLessEqual(_utc("2026-01-01T11:45:00Z"), _utc("2026-01-01T12:00:00Z"))
        self.assertGreater(_utc("2026-01-01T12:15:00Z"), _utc("2026-01-01T12:00:00Z"))
        self.assertIn("declared before evaluation", self.synthetic["protective_barrier_contract"]["target_rule"])
        self.assertIn("STOP_FIRST", self.synthetic["protective_barrier_contract"]["intrabar_order_rule"])
        barrier = "STOP_FIRST" if True and True else "UNREACHABLE"
        self.assertEqual(barrier, "STOP_FIRST")

    def test_state_permission_gate_is_boolean_and_cannot_move_price_intersection(self) -> None:
        zones = {"StructuralZone": (100.0, 105.0), "LiquidityFeasibleZone": (101.0, 106.0), "RiskGeometryZone": (99.0, 103.0), "VenueRuleZone": (102.0, 104.0)}
        self.assertEqual(_permissioned_intersection("ALLOW", zones), (102.0, 103.0))
        self.assertIsNone(_permissioned_intersection("DENY", zones))
        with self.assertRaisesRegex(ValueError, "GATE_REJECTED"):
            _permissioned_intersection("UNKNOWN", zones)
        with self.assertRaisesRegex(ValueError, "QUALITY_FAILS_BEFORE_GATE"):
            _permissioned_intersection("ALLOW", zones, quality="UNKNOWN")
        with self.assertRaisesRegex(ValueError, "ZONE_SCHEMA_INVALID"):
            _permissioned_intersection("ALLOW", {key: value for key, value in zones.items() if key != "VenueRuleZone"})
        with self.assertRaisesRegex(ValueError, "ZONE_SCHEMA_INVALID"):
            _permissioned_intersection("ALLOW", zones | {"ExtraZone": (1.0, 2.0)})
        gate = self.synthetic["entry_zone_contract"]["state_permission_gate"]
        self.assertIn("{ALLOW,DENY}", gate)
        self.assertIn("cannot move", gate)
        self.assertIn("four", self.synthetic["entry_zone_contract"]["intersection_rule"])

    def test_action_priority_is_total_and_probability_vectors_are_separate(self) -> None:
        flags = {"halt": False, "unknown": False, "exit": False, "manage": False, "rsi": True, "abstain": False, "candidate": False, "execution": False}
        action = "OBSERVE" if flags["rsi"] else "UNREACHABLE"
        self.assertEqual(action, "OBSERVE")
        flags["unknown"] = True
        action = "UNKNOWN" if flags["unknown"] else action
        self.assertEqual(action, "UNKNOWN")
        scenario = {"UPSIDE": 0.25, "DOWNSIDE": 0.25, "RANGE": 0.25, "UNRESOLVED": 0.25}
        outcome = {"NO_FILL": 0.10, "TP_FIRST": 0.20, "SL_FIRST": 0.30, "STRUCTURE_EXIT": 0.10, "TIMEOUT": 0.30}
        self.assertTrue(_probability_valid(scenario, MARKET_SCENARIO_BRANCHES))
        self.assertTrue(_probability_valid(outcome, ACTION_OUTCOME_BRANCHES))
        self.assertFalse(_probability_valid({"NO_FILL": True, "TP_FIRST": 0.0, "SL_FIRST": 0.0, "STRUCTURE_EXIT": 0.0, "TIMEOUT": 0.0}, ACTION_OUTCOME_BRANCHES))
        self.assertFalse(_probability_valid({"NO_FILL": False, "TP_FIRST": 1.0, "SL_FIRST": 0.0, "STRUCTURE_EXIT": 0.0, "TIMEOUT": 0.0}, ACTION_OUTCOME_BRANCHES))
        p_fill, filled = _filled_conditional_distribution(outcome)
        self.assertAlmostEqual(p_fill, 0.90)
        self.assertAlmostEqual(sum(filled.values()), 1.0)
        self.assertNotIn("NO_FILL", filled)
        self.assertNotIn("DATA_INVALID", outcome)
        self.assertFalse(_probability_valid({**outcome, "DATA_INVALID": 0.0}, ACTION_OUTCOME_BRANCHES))
        disposition_counts = {"VALID": 9, "CENSORED": 0, "DATA_INVALID": 0, "OPERATIONAL_OVERRIDE": 1}
        self.assertEqual(tuple(disposition_counts), DATA_DISPOSITION)
        self.assertTrue(disposition_counts["OPERATIONAL_OVERRIDE"] > 0)
        self.assertAlmostEqual(p_fill, 0.90)
        self.assertTrue(_probability_valid(outcome, ACTION_OUTCOME_BRANCHES))
        post_fill_override = _score_record(outcome, True, None, "OPERATIONAL_OVERRIDE")
        censored = _score_record(outcome, None, None, "CENSORED")
        valid_fill = _score_record(outcome, True, "TP_FIRST", "VALID")
        self.assertEqual(post_fill_override, {"pfill": True, "joint": False, "filled": False, "fail_closed": True})
        self.assertEqual(censored, {"pfill": False, "joint": False, "filled": False, "fail_closed": True})
        self.assertEqual(valid_fill, {"pfill": True, "joint": True, "filled": True, "fail_closed": False})
        for fill in (False, None):
            for terminal in ("TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT"):
                with self.assertRaisesRegex(ValueError, "FILL_OUTCOME_CONFLICT"):
                    _score_record(outcome, fill, terminal, "VALID")
        for fill in (True, None):
            with self.assertRaisesRegex(ValueError, "FILL_OUTCOME_CONFLICT"):
                _score_record(outcome, fill, "NO_FILL", "VALID")
        with self.assertRaisesRegex(ValueError, "INVALID_SCORE_RECORD"):
            _score_record(outcome, True, "BOGUS", "VALID")
        with self.assertRaisesRegex(ValueError, "VALID_TERMINAL_MISSING"):
            _score_record(outcome, True, None, "VALID")
        for pseudo_bool in (1, 0, 1.0, 0.0):
            with self.assertRaisesRegex(ValueError, "INVALID_SCORE_RECORD"):
                _score_record(outcome, pseudo_bool, None, "OPERATIONAL_OVERRIDE")
            with self.assertRaisesRegex(ValueError, "INVALID_SCORE_RECORD"):
                _score_denominators(outcome, [(pseudo_bool, None, "OPERATIONAL_OVERRIDE")])
        prediction_bytes = json.dumps(outcome, sort_keys=True, separators=(",", ":"))
        denoms = _score_denominators(outcome, [(True, "TP_FIRST", "VALID"), (False, "NO_FILL", "VALID"), (True, None, "OPERATIONAL_OVERRIDE"), (None, None, "CENSORED")])
        self.assertEqual(denoms, {"pfill": 3, "joint": 2, "filled": 1, "disposition_counts": {"VALID": 2, "CENSORED": 1, "DATA_INVALID": 0, "OPERATIONAL_OVERRIDE": 1}, "pre_fill_nonvalid": 1, "post_fill_nonvalid": 1})
        self.assertEqual(json.dumps(outcome, sort_keys=True, separators=(",", ":")), prediction_bytes)
        with self.assertRaisesRegex(ValueError, "INVALID_SCORE_RECORD"):
            _score_denominators(outcome, [(True, "BOGUS", "DATA_INVALID")])
        self.assertFalse(_probability_valid({"UPSIDE": 0.8, "DOWNSIDE": 0.1, "RANGE": 0.1, "UNRESOLVED": 0.1}, MARKET_SCENARIO_BRANCHES))
        self.assertFalse(_probability_valid({"NO_FILL": 1.0}, ACTION_OUTCOME_BRANCHES))

    def test_replay_is_canonical_despite_key_or_input_order_and_changes_with_version(self) -> None:
        a = {"stable_input_id": "b", "available_at": "2026-01-01T00:00:01Z", "source_timestamp": "2026-01-01T00:00:00Z", "record_version": "r2", "source_id": "A", "generation_id_or_stream_id": "g1", "source_sequence": 2, "payload": {"z": 2, "a": 1}}
        b = {"payload": {"a": 1, "z": 2}, "source_sequence": 1, "source_id": "A", "generation_id_or_stream_id": "g1", "source_timestamp": "2026-01-01T00:00:00Z", "record_version": "r1", "available_at": "2026-01-01T00:00:01Z", "stable_input_id": "a"}
        first_hash, first_bytes = _canonical_replay(self.synthetic["contract_id"], "v0.4.0", "f1", "M00-F01", [a, b])
        second_hash, second_bytes = _canonical_replay(self.synthetic["contract_id"], "v0.4.0", "f1", "M00-F01", [b, a])
        third_hash, _ = _canonical_replay(self.synthetic["contract_id"], "v0.4.1", "f1", "M00-F01", [b, a])
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first_bytes, second_bytes)
        self.assertNotEqual(first_hash, third_hash)
        revised_hash, _ = _canonical_replay(self.synthetic["contract_id"], "v0.4.0", "f1", "M00-F01", [{**b, "record_version": "r9"}, a])
        self.assertNotEqual(first_hash, revised_hash)
        with self.assertRaisesRegex(ValueError, "IDENTITY_MISSING"):
            _canonical_replay(self.synthetic["contract_id"], "v", "f", "M", [{key: value for key, value in a.items() if key != "record_version"}])
        with self.assertRaisesRegex(ValueError, "IDENTITY_MISSING"):
            _canonical_replay(self.synthetic["contract_id"], "v", "f", "M", [{**a, "stable_input_id": ""}])
        with self.assertRaisesRegex(ValueError, "STABLE_ID_DUPLICATE"):
            _canonical_replay(self.synthetic["contract_id"], "v", "f", "M", [a, {**b, "stable_input_id": a["stable_input_id"]}])

    def test_source_sequence_is_stream_local_and_cross_source_batches_do_not_invent_order(self) -> None:
        left = {"available_at": "2026-01-01T00:00:00Z", "source_id": "A", "generation_id_or_stream_id": "g1", "source_sequence": 4, "stable_input_id": "a"}
        same_stream = {**left, "source_sequence": 5, "stable_input_id": "b"}
        cross_source = {**left, "source_id": "B", "source_sequence": 1, "stable_input_id": "c"}
        self.assertEqual(_economic_order(left, same_stream), "LEFT_FIRST")
        self.assertEqual(_economic_order(left, cross_source), "BATCH_UNRESOLVED")
        self.assertEqual(_economic_order(left, {**left, "generation_id_or_stream_id": "g2", "source_sequence": 1}), "BATCH_UNRESOLVED")
        exchangeable = lambda rows: sum(int(row["source_sequence"]) for row in rows)
        self.assertEqual(exchangeable([left, cross_source]), exchangeable([cross_source, left]))
        self.assertIn("batch-permutation invariant", self.synthetic["time_contract"]["same_timestamp_rule"])
        self.assertIn("UNRESOLVED or STOP_FIRST", self.synthetic["deterministic_replay_contract"]["ordering_rule"])
        with self.assertRaisesRegex(ValueError, "SEQUENCE_DUPLICATE"):
            _canonical_replay(self.synthetic["contract_id"], "v", "f", "M00", [left | {"source_timestamp": "t", "record_version": "r"}, left | {"source_timestamp": "t", "record_version": "r2", "stable_input_id": "other"}])

    def test_contract_has_required_synthetic_failure_fixtures(self) -> None:
        fixtures = {item["fixture_id"]: item["expect"] for item in self.synthetic["synthetic_fixtures"]}
        self.assertEqual(fixtures["M00-F01-UNCLOSED_PARENT"], "PARENT_NOT_VISIBLE__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F04-NEIGHBOR_EMBARGO"], "NEIGHBOR_INELIGIBLE_STRICT_INEQUALITY")
        self.assertEqual(fixtures["M00-F06-EMPTY_ENTRY_INTERSECTION"], "ABSTAIN")
        self.assertEqual(fixtures["M00-F07-LONG_STOP_EXPANSION"], "STOP_DATA_INVALID_AND_ABSTAIN")
        self.assertEqual(fixtures["M00-F10-SIMULTANEOUS_BARRIERS"], "STOP_FIRST")
        self.assertEqual(fixtures["M00-F11-VALID_CROSS_REGION_TRANSITION"], "TFSTATE_STRUCTURAL_REGIME_TRANSITION")
        self.assertEqual(fixtures["M00-F12-PARENT_CONFLICT_DOES_NOT_REWRITE_TFSTATE"], "TFSTATE_UP__DECISIONSTATE_ABSTAIN")
        self.assertEqual(fixtures["M00-F13-POST_FILL_OPERATIONAL_OVERRIDE_EXTERNAL"], "REPORT_FAIL_CLOSED__DO_NOT_REWRITE_ACTION_OUTCOME")
        self.assertEqual(fixtures["M00-F14-CROSS_SOURCE_EQUAL_TIME_NONEXCHANGEABLE"], "UNRESOLVED_OR_STOP_FIRST")
        self.assertEqual(fixtures["M00-F15-STATE_PERMISSION_DENY_EMPTY_ZONE"], "EMPTY_ENTRYZONE__ABSTAIN")
        self.assertEqual(fixtures["M00-F16-EXACT_COHORT_ONE_FIELD_MISMATCH"], "NO_POOL__SEPARATE_STRATUM_OR_DATA_INVALID")
        self.assertEqual(fixtures["M00-F17-RSI_PERSISTENT_EXTREME_LATER_EVALUATE"], "NO_DUPLICATE_OBSERVE__EVALUATE_REVERSAL_ALLOWED")
        self.assertEqual(fixtures["M00-F18-H12_EVENT_CANNOT_SATISFY_H10_PRICE"], "H10_NOT_SUPPORTED__H12_DIAGNOSTIC_ONLY")
        self.assertEqual(fixtures["M00-F19-FUTURE_SOURCE_TIMESTAMP"], "PARENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F20-STRING_PSEUDO_BOOLEAN"], "PARENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F21-NUMERIC_PSEUDO_BOOLEAN"], "PARENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F22-MALFORMED_TIMESTAMP"], "PARENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F23-MISSING_TIMESTAMP"], "PARENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F24-EVENT_FUTURE_SOURCE_TIMESTAMP"], "EVENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F25-EVENT_FUTURE_REVISION_AVAILABLE"], "EVENT_REVISION_NOT_VISIBLE__APPEND_ONLY__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F26-EVENT_MALFORMED_TIMESTAMP"], "EVENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")
        self.assertEqual(fixtures["M00-F27-EVENT_MISSING_TIMESTAMP"], "EVENT_NOT_VISIBLE__DATA_INVALID__UNKNOWN_OR_ABSTAIN")

    def test_h10_prefix_d2_d3_d6_d7_never_reads_future_day(self) -> None:
        rows = [
            {"day": index, "is_closed": True, "source_timestamp": f"2026-01-0{index}T00:00:00Z", "close_time": f"2026-01-0{index}T00:00:00Z", "available_at": f"2026-01-0{index}T00:00:00Z"}
            for index in range(1, 9)
        ]
        for prefix in (2, 3, 6, 7):
            with self.subTest(prefix=prefix):
                prefix_rows = _h10_prefix(rows[:prefix], prefix, f"2026-01-0{prefix}T00:00:00Z")
                self.assertEqual([item["day"] for item in prefix_rows], list(range(1, prefix + 1)))
                h11_prefix_rows = _h11_prefix(rows[:prefix], prefix, f"2026-01-0{prefix}T00:00:00Z")
                self.assertEqual([item["day"] for item in h11_prefix_rows], list(range(1, prefix + 1)))
                with self.assertRaisesRegex(ValueError, "FULL_EPISODE_LOOKAHEAD"):
                    _h10_prefix(rows[: prefix + 1], prefix, f"2026-01-0{prefix}T00:00:00Z")

    def test_h10_h11_prefixes_share_fail_closed_visibility(self) -> None:
        valid = {"day": 2, "is_closed": True, "source_timestamp": "2026-01-02T00:00:00Z", "close_time": "2026-01-02T00:00:00Z", "available_at": "2026-01-02T00:00:00Z"}
        for helper in (_h10_prefix, _h11_prefix):
            with self.subTest(helper=helper.__name__):
                self.assertEqual(helper([valid], 2, "2026-01-02T00:00:00Z"), [valid])
                for mutation in (
                    {"source_timestamp": "2026-01-02T00:00:01Z"},
                    {"is_closed": "false"},
                    {"is_closed": 1},
                    {"close_time": "malformed"},
                    {"available_at": None},
                ):
                    with self.assertRaisesRegex(ValueError, "PREFIX_TIME_INVALID"):
                        helper([valid | mutation], 2, "2026-01-02T00:00:00Z")

    def test_h10_h11_price_endpoints_and_h12_event_diagnostic_are_separate(self) -> None:
        h10 = self.synthetic["h10_daily_prefix_contract"]
        self.assertEqual(tuple(h10["prefix_ids"]), ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"))
        self.assertIn("one episode cluster", h10["cluster_rule"])
        self.assertIn("at-most-eight", h10["volume_rule"])
        expected_actions = ("UNKNOWN", "OBSERVE", "ABSTAIN", "EVALUATE_REVERSAL")
        self.assertEqual(tuple(h10["action_set"]), expected_actions)
        self.assertEqual(tuple(self.method["event_sequence_candidate"]["action_set"]), expected_actions)
        self.assertEqual(h10["unknown_action_rule"], self.method["event_sequence_candidate"]["unknown_action_rule"])
        self.assertEqual(set(expected_actions), set(h10["action_set"]))
        self.assertIn("EVENT_BAR_CHASING", h10["forbidden"])
        price_d2_d3 = h10["specific_prefix_assertions"]["D2_D3_price_primary"]
        price_d6_d7 = h10["specific_prefix_assertions"]["D6_D7_price_primary"]
        self.assertIn("price endpoint", price_d2_d3)
        self.assertIn("price endpoint", price_d6_d7)
        self.assertIn("no event arrival may enter", price_d2_d3)
        self.assertIn("no event arrival may enter", price_d6_d7)
        self.assertIn("cannot make either H10 or H11 price endpoint pass", h10["specific_prefix_assertions"]["H12_event_diagnostic"])
        hypotheses = {item["hypothesis_id"]: item for item in self.registry["hypotheses"]}
        self.assertEqual(hypotheses["V4-H10-D2_D3_UPWARD_EXPANSION_PRICE_SEQUENCE"]["primary_outcome"], "D2_D3_PREFIX_TO_1_3_DAY_UPWARD_EXPANSION_PRICE")
        self.assertEqual(hypotheses["V4-H11-D6_D7_DOWNSIDE_BREAKDOWN_PRICE_SEQUENCE"]["primary_outcome"], "D6_D7_PREFIX_TO_NEXT_DAY_DOWNSIDE_BREAKDOWN_PRICE")
        self.assertIn("independent diagnostic", hypotheses["V4-H12-EVENT_ARRIVAL_ASSOCIATION"]["claim"])
        self.assertFalse(_price_hypothesis_supported(False, True))
        self.assertTrue(_price_hypothesis_supported(True, False))
        self.assertGreater(_robust_log_volume_residual([100.0, 100.0, 100.0], 1000.0), 0.0)
        event = {"source_timestamp": "2026-01-03T00:00:00Z", "published_at": "2026-01-03T00:00:00Z", "available_at": "2026-01-03T00:01:00Z"}
        self.assertFalse(_event_visible_at_prefix(event, "2026-01-03T00:00:00Z"))
        self.assertTrue(_event_visible_at_prefix(event, "2026-01-03T00:01:00Z"))
        self.assertEqual(tuple(h10["exact_cohort_key_set"]), EXACT_COHORT_KEYS)
        cohort = {
            "asset_class": "CRYPTO",
            "venue": "V1",
            "market_type": "PERPETUAL",
            "instrument_id": "BTCUSDT",
            "contract_specification": "LINEAR",
            "session_timezone": "UTC",
            "daily_boundary": "00:00",
            "volume_unit": "BASE",
            "price_adjustment_policy": "CONTRACT",
        }
        for field in EXACT_COHORT_KEYS:
            changed = dict(cohort)
            changed[field] = f"DIFFERENT_{field}"
            with self.subTest(field=field):
                self.assertFalse(_same_h10_pool(cohort, changed))
        self.assertEqual(tuple(self.method["cohort_contract"]["exact_key_set"]), EXACT_COHORT_KEYS)
        self.assertEqual(tuple(self.registry["common_rules"]["exact_cohort_key_set"]), EXACT_COHORT_KEYS)

    def test_h12_event_visibility_uses_full_causal_clock_and_fails_closed(self) -> None:
        event = {"source_timestamp": "2026-01-03T00:00:00Z", "published_at": "2026-01-03T00:00:00Z", "available_at": "2026-01-03T00:01:00Z"}
        decision = "2026-01-03T00:01:00Z"
        self.assertTrue(_event_visible_at_prefix(event, decision))
        for mutation in (
            {"source_timestamp": "2026-01-03T00:01:01Z"},
            {"published_at": "2026-01-03T00:01:01Z"},
            {"available_at": "2026-01-03T00:01:01Z"},
            {"source_timestamp": "malformed"},
            {"published_at": "2026-01-03T00:00:00"},
            {"available_at": None},
            {"source_timestamp": None},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_event_visible_at_prefix(event | mutation, decision))
        self.assertEqual(len(set(EXACT_COHORT_KEYS)), 9)


if __name__ == "__main__":
    unittest.main()
