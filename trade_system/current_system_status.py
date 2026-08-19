"""Validate the present-day status overlay without rewriting historical evidence."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CurrentSystemStatusError(ValueError):
    """The status overlay or one of its evidence bindings is inconsistent."""


_TOP_LEVEL_FIELDS = {
    "schema_version",
    "status_id",
    "as_of_date",
    "status",
    "precedence",
    "core",
    "decision_timeline",
    "rsi_v0_2_2_lineage",
    "runtime",
    "lane_boundaries",
    "release_contract",
    "evidence_bindings",
}

_ROLE_PATHS = {
    "CORE_AUTHORITY_REGISTRY": "config/core_trading_theory.authority.v2_1.json",
    "CORE_VERSIONED_BYTES": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
    "CORE_ROOT_MIRROR_BYTES": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
    "DYNAMIC_HYPOTHESIS_GRAPH_P0_1_GATE": "config/sol_decision.research-system-dynamic-hypothesis-graph-p0_1-gate.v1.json",
    "PIT_AUTHORITY_REPLAY_E0_GATE": "config/sol_decision.research-system-pit-authority-replay-e0-gate.v1.json",
    "SD0_R8_COMPLETION": "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion.v1.json",
    "HAR1R4_EVIDENCE_MANIFEST": "har1r4/evidence/manifest.json",
    "HAR1R5_STATIC_ROUTE": "config/sol_decision.har1r5-raw-license-candidate-route.v1.json",
    "ACTIVE_G1_TERMINAL": "config/sol_decision.active-g1-plan-unreachable.v2.json",
    "FEBRUARY_A2F1_TERMINAL_DECISION": "config/sol_decision.s0-009-r1-acquisition-gap-censoring.a2f1.json",
    "FEBRUARY_TERMINAL_GUARD": "config/s0_009_february_terminal_seen_guard.a3e1.json",
    "RSI_V0_2_2_STRATEGY_CONTRACT": "config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json",
    "RSI_V0_2_2_ROUTE_DECISION": "config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json",
    "RSI_V0_2_RESEARCH_CONTRACT": "config/rsi_mtf_drl_pm.research_contract.v0_2.json",
    "RSI_V0_2_FROZEN_CORE": "archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md",
    "RSI_V0_2_FROZEN_LEGACY_TEST": "archive/authority/tests/test_rsi_research_contract.v0_2.py",
}


def _reject_constant(value: str) -> None:
    raise CurrentSystemStatusError(f"non-finite JSON constant is forbidden: {value}")


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CurrentSystemStatusError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentSystemStatusError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CurrentSystemStatusError(f"{label} must be a JSON object")
    return value


def _relative_file(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise CurrentSystemStatusError(f"{label} must be a non-empty relative path")
    resolved_root = root.resolve()
    target = (resolved_root / relative).resolve()
    if resolved_root not in target.parents or not target.is_file():
        raise CurrentSystemStatusError(f"{label} must resolve to a workspace file")
    return target


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentSystemStatusError(f"{label} must be an object")
    return value


def _expect(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        raise CurrentSystemStatusError(f"{label} drifted")


def _load_bound_json(root: Path, bindings: Mapping[str, Mapping[str, Any]], role: str) -> dict[str, Any]:
    path = _relative_file(root, bindings[role]["path"], role)
    return _load_json_bytes(path.read_bytes(), role)


def validate_current_system_status(value: Mapping[str, Any], workspace_root: Path) -> dict[str, Any]:
    """Validate the overlay, its bound bytes, and the cross-document state claims."""
    root = Path(workspace_root).resolve()
    if set(value) != _TOP_LEVEL_FIELDS:
        raise CurrentSystemStatusError("status overlay top-level fields are not closed")
    _expect(value["schema_version"], "current-system-status.v1", "schema_version")
    _expect(value["status_id"], "CURRENT_SYSTEM_STATUS.v1", "status_id")
    _expect(value["as_of_date"], "2026-07-30", "as_of_date")
    _expect(
        value["status"],
        "VERSIONED_RESEARCH_BASELINE_WITH_ISOLATED_PAPER_EXPERIMENT",
        "status",
    )
    precedence = value["precedence"]
    if not isinstance(precedence, list) or len(precedence) != 3 or not all(
        isinstance(item, str) and item for item in precedence
    ):
        raise CurrentSystemStatusError("precedence must contain exactly three non-empty rules")

    raw_bindings = value["evidence_bindings"]
    if not isinstance(raw_bindings, list) or len(raw_bindings) != len(_ROLE_PATHS):
        raise CurrentSystemStatusError("evidence_bindings must contain the exact role set")
    bindings: dict[str, Mapping[str, Any]] = {}
    for index, raw_binding in enumerate(raw_bindings):
        binding = _mapping(raw_binding, f"evidence_bindings[{index}]")
        if set(binding) != {"role", "path", "size_bytes", "sha256"}:
            raise CurrentSystemStatusError("evidence binding fields are not closed")
        role = binding["role"]
        if not isinstance(role, str) or role in bindings or role not in _ROLE_PATHS:
            raise CurrentSystemStatusError("evidence binding role is missing, duplicate, or unknown")
        _expect(binding["path"], _ROLE_PATHS[role], f"{role}.path")
        if type(binding["size_bytes"]) is not int or binding["size_bytes"] <= 0:
            raise CurrentSystemStatusError(f"{role}.size_bytes must be a positive integer")
        if not isinstance(binding["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]) is None:
            raise CurrentSystemStatusError(f"{role}.sha256 must be lowercase SHA-256")
        path = _relative_file(root, binding["path"], role)
        raw = path.read_bytes()
        _expect(len(raw), binding["size_bytes"], f"{role}.size_bytes")
        _expect(_sha256(raw), binding["sha256"], f"{role}.sha256")
        bindings[role] = binding
    if set(bindings) != set(_ROLE_PATHS):
        raise CurrentSystemStatusError("evidence binding role closure failed")

    core = _mapping(value["core"], "core")
    if set(core) != {
        "current_id",
        "current_status",
        "authority_registry_path",
        "versioned_path",
        "root_mirror_path",
        "raw_sha256",
        "size_bytes",
    }:
        raise CurrentSystemStatusError("core fields are not closed")
    _expect(core["current_id"], "CORE_TRADING_THEORY.v2.1", "core.current_id")
    _expect(core["current_status"], "CURRENT_IMMUTABLE_AUTHORITY", "core.current_status")
    authority = _load_bound_json(root, bindings, "CORE_AUTHORITY_REGISTRY")
    for field, expected in (
        ("id", core["current_id"]),
        ("status", core["current_status"]),
        ("path", core["versioned_path"]),
        ("root_mirror_path", core["root_mirror_path"]),
        ("raw_sha256", core["raw_sha256"]),
        ("size_bytes", core["size_bytes"]),
    ):
        _expect(authority.get(field), expected, f"core authority {field}")
    _expect(core["authority_registry_path"], bindings["CORE_AUTHORITY_REGISTRY"]["path"], "core authority path")
    _expect(core["versioned_path"], bindings["CORE_VERSIONED_BYTES"]["path"], "core versioned path")
    _expect(core["root_mirror_path"], bindings["CORE_ROOT_MIRROR_BYTES"]["path"], "core mirror path")
    _expect(core["raw_sha256"], bindings["CORE_VERSIONED_BYTES"]["sha256"], "core versioned digest")
    _expect(core["raw_sha256"], bindings["CORE_ROOT_MIRROR_BYTES"]["sha256"], "core mirror digest")
    _expect(core["size_bytes"], bindings["CORE_VERSIONED_BYTES"]["size_bytes"], "core versioned size")
    _expect(core["size_bytes"], bindings["CORE_ROOT_MIRROR_BYTES"]["size_bytes"], "core mirror size")

    timeline = _mapping(value["decision_timeline"], "decision_timeline")
    if set(timeline) != {
        "dynamic_hypothesis_graph_p0_1",
        "pit_authority_replay_e0",
        "sd0_r8",
        "har1r4",
        "har1r5",
        "active_g1",
        "february_historical_diagnostic",
    }:
        raise CurrentSystemStatusError("decision timeline fields are not closed")
    timeline_checks = (
        (
            "dynamic_hypothesis_graph_p0_1",
            "DYNAMIC_HYPOTHESIS_GRAPH_P0_1_GATE",
            "ACCEPT_P0_1",
            "EXACT_BOUND_E0_PACKAGE_ACCEPTED_CORE_V2_1_UNCHANGED_NO_MARKET_PROOF",
        ),
        (
            "pit_authority_replay_e0",
            "PIT_AUTHORITY_REPLAY_E0_GATE",
            "ACCEPT_PITAR1_E0_CONTRACT_SD0_WAIT_DATA_D0_DENIED",
            "EXACT_E0_CONTRACT_ACCEPTED_SOURCE_AND_D0_REMAIN_WAIT_DATA",
        ),
        (
            "sd0_r8",
            "SD0_R8_COMPLETION",
            "ACCEPT_R8_EXACT_POST_PATCH_CALL_LAYER_ROUTE_AUTHORIZE_CAPABILITY_SCOPED_SD0_PREFLIGHT_AND_SEVEN_REQUESTS",
            "HISTORICAL_TIME_BOUND_CAPABILITY_COMPLETION_OUTPUTS_MAY_NOW_EXIST_NO_D0_OR_MARKET_ROW_AUTHORITY",
        ),
        (
            "active_g1",
            "ACTIVE_G1_TERMINAL",
            "TERMINAL_WAIT_DATA_PLAN_UNREACHABLE",
            "FROZEN_ACTIVE_G1_PLAN_PRESERVED_NO_BACKFILL_OR_RECOVERY_AUTHORITY",
        ),
    )
    for name, role, decision_state, interpretation in timeline_checks:
        row = _mapping(timeline[name], f"decision_timeline.{name}")
        expected_fields = {"path", "decision_state", "current_interpretation"}
        if name == "sd0_r8":
            expected_fields.add("activation_expired_at")
        if set(row) != expected_fields:
            raise CurrentSystemStatusError(f"{name} timeline fields are not closed")
        _expect(row.get("path"), bindings[role]["path"], f"{name}.path")
        _expect(row.get("decision_state"), decision_state, f"{name}.decision_state")
        _expect(row.get("current_interpretation"), interpretation, f"{name}.current_interpretation")
        decision = _load_bound_json(root, bindings, role)
        _expect(decision.get("decision_state"), decision_state, f"{role} decision_state")
    p0_gate = _load_bound_json(root, bindings, "DYNAMIC_HYPOTHESIS_GRAPH_P0_1_GATE")
    _expect(
        p0_gate.get("stage_disposition", {}).get("p0_1_accepted_for_exact_bound_e0_package"),
        True,
        "P0.1 acceptance",
    )
    _expect(p0_gate.get("stage_disposition", {}).get("challenger_promoted_to_core"), False, "P0.1 core promotion")
    pit_gate = _load_bound_json(root, bindings, "PIT_AUTHORITY_REPLAY_E0_GATE")
    _expect(pit_gate.get("stage_disposition", {}).get("pitar1_e0_contract_accepted"), True, "PITAR1 E0 acceptance")
    _expect(pit_gate.get("stage_disposition", {}).get("d0_authorized"), False, "PITAR1 D0 authority")
    sd0 = _load_bound_json(root, bindings, "SD0_R8_COMPLETION")
    _expect(timeline["sd0_r8"].get("activation_expired_at"), sd0.get("activation", {}).get("expires_at_utc"), "SD0 expiry")
    _expect(sd0.get("permission_matrix", {}).get("d0"), False, "SD0 D0 authority")
    har1r4_row = _mapping(timeline["har1r4"], "HAR1R4 timeline")
    if set(har1r4_row) != {
        "path",
        "aggregate_outcome",
        "repository_state",
        "terms_state",
        "legal_conclusion",
        "current_interpretation",
    }:
        raise CurrentSystemStatusError("HAR1R4 timeline fields are not closed")
    _expect(har1r4_row.get("path"), bindings["HAR1R4_EVIDENCE_MANIFEST"]["path"], "HAR1R4 path")
    _expect(har1r4_row.get("aggregate_outcome"), "FAILURE", "HAR1R4 aggregate outcome")
    _expect(
        har1r4_row.get("repository_state"),
        "WAIT_DATA_SOURCE_CONTRACT_MISMATCH",
        "HAR1R4 repository state",
    )
    _expect(har1r4_row.get("terms_state"), "WAIT_DATA_TERMS_D0_DENIED", "HAR1R4 terms state")
    _expect(har1r4_row.get("legal_conclusion"), False, "HAR1R4 legal conclusion")
    _expect(
        har1r4_row.get("current_interpretation"),
        "SEALED_R4_REQUEST_RESULT_FAILED_NO_SOURCE_TERMS_OR_LEGAL_AUTHORITY",
        "HAR1R4 interpretation",
    )
    har1r4 = _load_bound_json(root, bindings, "HAR1R4_EVIDENCE_MANIFEST")
    for field in ("aggregate_outcome", "repository_state", "terms_state", "legal_conclusion"):
        _expect(har1r4.get(field), har1r4_row.get(field), f"HAR1R4 {field}")
    har1r5_row = _mapping(timeline["har1r5"], "HAR1R5 timeline")
    if set(har1r5_row) != {"path", "decision_state", "current_interpretation"}:
        raise CurrentSystemStatusError("HAR1R5 timeline fields are not closed")
    _expect(har1r5_row.get("path"), bindings["HAR1R5_STATIC_ROUTE"]["path"], "HAR1R5 path")
    _expect(
        har1r5_row.get("decision_state"),
        "AUTHORIZE_HAR1R5_STATIC_GATE_ONLY_NO_NETWORK",
        "HAR1R5 decision state",
    )
    _expect(
        har1r5_row.get("current_interpretation"),
        "STATIC_ROUTE_ONLY_NETWORK_ACTIVATION_DATA_BACKTEST_AND_TRADING_DENIED",
        "HAR1R5 interpretation",
    )
    har1r5 = _load_bound_json(root, bindings, "HAR1R5_STATIC_ROUTE")
    _expect(har1r5.get("decision_state"), har1r5_row.get("decision_state"), "HAR1R5 decision state")
    for field in ("network_now", "activation_now", "data", "backtest", "trading"):
        _expect(har1r5.get("permission_matrix", {}).get(field), False, f"HAR1R5 {field} permission")
    active_g1 = _load_bound_json(root, bindings, "ACTIVE_G1_TERMINAL")
    _expect(active_g1.get("stage_gate_disposition", {}).get("new_lane_authorized"), False, "active G1 new lane authority")
    february_row = _mapping(timeline["february_historical_diagnostic"], "February timeline")
    if set(february_row) != {
        "decision_path",
        "decision_state",
        "execution_gate",
        "guard_path",
        "guard_status",
        "current_interpretation",
    }:
        raise CurrentSystemStatusError("February timeline fields are not closed")
    _expect(
        february_row.get("decision_path"),
        bindings["FEBRUARY_A2F1_TERMINAL_DECISION"]["path"],
        "February decision path",
    )
    _expect(february_row.get("guard_path"), bindings["FEBRUARY_TERMINAL_GUARD"]["path"], "February guard path")
    _expect(
        february_row.get("decision_state"),
        "FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED",
        "February decision state",
    )
    _expect(
        february_row.get("execution_gate"),
        "HOLD_BEFORE_ANY_NEW_ACQUISITION_OR_SCORING",
        "February execution gate",
    )
    _expect(february_row.get("guard_status"), "ACTIVE_FAIL_CLOSED", "February guard status")
    _expect(
        february_row.get("current_interpretation"),
        "TERMINAL_SEEN_GUARD_REMAINS_ACTIVE_TEST_FIXTURES_MUST_NOT_WEAKEN_PRODUCTION",
        "February interpretation",
    )
    february_decision = _load_bound_json(root, bindings, "FEBRUARY_A2F1_TERMINAL_DECISION")
    _expect(
        february_decision.get("execution_state"),
        february_row.get("decision_state"),
        "February decision execution state",
    )
    _expect(
        february_decision.get("execution_gate"),
        february_row.get("execution_gate"),
        "February decision execution gate",
    )
    february = _load_bound_json(root, bindings, "FEBRUARY_TERMINAL_GUARD")
    _expect(february.get("status"), february_row.get("guard_status"), "February terminal guard")

    lineage = _mapping(value["rsi_v0_2_2_lineage"], "rsi_v0_2_2_lineage")
    expected_lineage_fields = {
        "status",
        "strategy_contract_path",
        "route_decision_path",
        "research_contract_path",
        "declared_core_path",
        "declared_core_raw_sha256",
        "declared_core_size_bytes",
        "archived_core_path",
        "archived_legacy_test_path",
        "physical_research_contract_status",
        "physical_research_contract_freeze_eligibility",
        "current_route_status",
        "current_route_phase",
        "direct_ast_disposition",
        "immutable_contract_bytes_changed",
        "validation_mode",
    }
    if set(lineage) != expected_lineage_fields:
        raise CurrentSystemStatusError("RSI lineage fields are not closed")
    _expect(
        lineage["status"],
        "IMMUTABLE_LEGACY_PACKAGE_REPRODUCIBLE_IN_ISOLATED_WORKSPACE",
        "RSI lineage status",
    )
    _expect(lineage["strategy_contract_path"], bindings["RSI_V0_2_2_STRATEGY_CONTRACT"]["path"], "RSI strategy path")
    _expect(lineage["route_decision_path"], bindings["RSI_V0_2_2_ROUTE_DECISION"]["path"], "RSI route path")
    _expect(lineage["research_contract_path"], bindings["RSI_V0_2_RESEARCH_CONTRACT"]["path"], "RSI research path")
    _expect(lineage["archived_core_path"], bindings["RSI_V0_2_FROZEN_CORE"]["path"], "RSI archived core path")
    _expect(lineage["archived_legacy_test_path"], bindings["RSI_V0_2_FROZEN_LEGACY_TEST"]["path"], "RSI archived test path")
    _expect(lineage["immutable_contract_bytes_changed"], False, "RSI immutable contract mutation")
    _expect(
        lineage["validation_mode"],
        "COPY_FROZEN_INPUTS_TO_ISOLATED_WORKSPACE_THEN_VALIDATE_BASELINE_BEFORE_TAMPER",
        "RSI validation mode",
    )
    strategy = _load_bound_json(root, bindings, "RSI_V0_2_2_STRATEGY_CONTRACT")
    route = _load_bound_json(root, bindings, "RSI_V0_2_2_ROUTE_DECISION")
    research = _load_bound_json(root, bindings, "RSI_V0_2_RESEARCH_CONTRACT")
    _expect(
        lineage["physical_research_contract_status"],
        "REVIEW_READY",
        "RSI physical research contract status",
    )
    _expect(
        lineage["physical_research_contract_freeze_eligibility"],
        "REJECT_FREEZE",
        "RSI physical research contract freeze eligibility",
    )
    _expect(lineage["current_route_status"], "SOL_ROUTE_B_ADOPTED", "RSI current route status")
    _expect(
        lineage["current_route_phase"],
        "AUTHORITY_BUNDLE_CONTRACT_DRAFTING",
        "RSI current route phase",
    )
    _expect(
        lineage["direct_ast_disposition"],
        "HISTORICAL_REWORK_NON_AUTHORITY",
        "RSI Direct AST disposition",
    )
    _expect(research.get("status"), lineage["physical_research_contract_status"], "RSI research status")
    _expect(
        research.get("freeze_eligibility"),
        lineage["physical_research_contract_freeze_eligibility"],
        "RSI research freeze eligibility",
    )
    _expect(route.get("status"), lineage["current_route_status"], "RSI route status")
    _expect(
        route.get("active_state", {}).get("phase"),
        lineage["current_route_phase"],
        "RSI route phase",
    )
    _expect(
        route.get("direct_ast_disposition", {}).get("artifact_status"),
        lineage["direct_ast_disposition"],
        "RSI Direct AST disposition",
    )
    _expect(
        strategy.get("route_decision_raw_sha256"),
        bindings["RSI_V0_2_2_ROUTE_DECISION"]["sha256"],
        "RSI strategy route decision digest",
    )
    source = _mapping(strategy.get("source_authority"), "RSI strategy source_authority")
    frozen_core = _mapping(route.get("frozen_inputs", {}).get("core_theory"), "RSI route core")
    for field, expected in (
        ("path", lineage["declared_core_path"]),
        ("raw_sha256", lineage["declared_core_raw_sha256"]),
        ("size_bytes", lineage["declared_core_size_bytes"]),
    ):
        _expect(frozen_core.get(field), expected, f"RSI route core {field}")
        _expect(source.get(f"core_theory_{field}"), expected, f"RSI strategy core {field}")
    _expect(bindings["RSI_V0_2_FROZEN_CORE"]["sha256"], lineage["declared_core_raw_sha256"], "RSI archived core digest")
    _expect(bindings["RSI_V0_2_FROZEN_CORE"]["size_bytes"], lineage["declared_core_size_bytes"], "RSI archived core size")
    review_bindings = research.get("review_tooling_binding", {}).get("bindings", [])
    core_review = next(
        (
            item
            for item in review_bindings
            if isinstance(item, dict) and item.get("path") == lineage["declared_core_path"]
        ),
        None,
    )
    if core_review is None:
        raise CurrentSystemStatusError("RSI research contract lacks the legacy Core binding")
    _expect(core_review.get("sha256"), lineage["declared_core_raw_sha256"], "RSI research Core digest")
    frozen_test = _mapping(
        route.get("frozen_inputs", {}).get("legacy_v0_2_contract_test"),
        "RSI frozen legacy test",
    )
    _expect(
        frozen_test.get("raw_sha256"),
        bindings["RSI_V0_2_FROZEN_LEGACY_TEST"]["sha256"],
        "RSI archived legacy test digest",
    )
    _expect(
        frozen_test.get("size_bytes"),
        bindings["RSI_V0_2_FROZEN_LEGACY_TEST"]["size_bytes"],
        "RSI archived legacy test size",
    )

    runtime = _mapping(value["runtime"], "runtime")
    if set(runtime) != {"python_requires", "primary_validation_runtime", "dependency_policy"}:
        raise CurrentSystemStatusError("runtime fields are not closed")
    _expect(runtime.get("python_requires"), ">=3.11,<3.14", "runtime.python_requires")
    _expect(runtime.get("primary_validation_runtime"), "Python 3.12", "runtime validation runtime")
    _expect(runtime.get("dependency_policy"), "STDLIB_FIRST", "runtime dependency policy")
    pyproject = tomllib.loads(_relative_file(root, "pyproject.toml", "pyproject.toml").read_text(encoding="utf-8"))
    _expect(pyproject.get("project", {}).get("requires-python"), runtime["python_requires"], "pyproject Python range")
    setup_source = _relative_file(root, "setup.py", "setup.py").read_text(encoding="utf-8")
    setup_match = re.search(r'python_requires="([^"]+)"', setup_source)
    _expect(setup_match.group(1) if setup_match else None, runtime["python_requires"], "setup.py Python range")

    lanes = _mapping(value["lane_boundaries"], "lane_boundaries")
    if set(lanes) != {"legacy_hash_bound_research", "new_theory_paper_experiment"}:
        raise CurrentSystemStatusError("lane boundaries are not closed")
    legacy_lane = _mapping(lanes["legacy_hash_bound_research"], "legacy lane")
    paper_lane = _mapping(lanes["new_theory_paper_experiment"], "paper lane")
    if set(legacy_lane) != {"paper_authorized", "live_trading_authorized", "maximum_claim"}:
        raise CurrentSystemStatusError("legacy lane fields are not closed")
    if set(paper_lane) != {
        "authority_basis",
        "scope",
        "paper_authorized",
        "live_trading_authorized",
        "profit_guaranteed",
        "maximum_claim",
    }:
        raise CurrentSystemStatusError("paper lane fields are not closed")
    _expect(legacy_lane.get("paper_authorized"), False, "legacy paper authority")
    _expect(legacy_lane.get("live_trading_authorized"), False, "legacy live authority")
    _expect(
        paper_lane.get("authority_basis"),
        "EXPLICIT_USER_REQUEST_2026-07-30",
        "paper lane authority basis",
    )
    _expect(paper_lane.get("scope"), "ISOLATED_PUBLIC_DATA_PAPER_ONLY", "paper lane scope")
    _expect(paper_lane.get("paper_authorized"), True, "paper lane paper authority")
    _expect(paper_lane.get("live_trading_authorized"), False, "paper lane live authority")
    _expect(paper_lane.get("profit_guaranteed"), False, "paper lane profit guarantee")

    release = _mapping(value["release_contract"], "release_contract")
    if set(release) != {
        "source_of_truth",
        "full_suite_required",
        "working_tree_snapshot_alone_is_release",
        "historical_documents_rewritten_for_status_sync",
    }:
        raise CurrentSystemStatusError("release contract fields are not closed")
    _expect(
        release.get("source_of_truth"),
        "VERSIONED_COMMIT_PLUS_THIS_VALIDATED_OVERLAY",
        "release source of truth",
    )
    _expect(release.get("full_suite_required"), True, "release full-suite requirement")
    _expect(release.get("working_tree_snapshot_alone_is_release"), False, "working-tree release claim")
    _expect(release.get("historical_documents_rewritten_for_status_sync"), False, "historical rewrite claim")

    return {
        "status_id": value["status_id"],
        "status": value["status"],
        "core_id": core["current_id"],
        "core_sha256": core["raw_sha256"],
        "p0_1_state": timeline["dynamic_hypothesis_graph_p0_1"]["decision_state"],
        "pit_e0_state": timeline["pit_authority_replay_e0"]["decision_state"],
        "har1r4_outcome": timeline["har1r4"]["aggregate_outcome"],
        "har1r5_state": timeline["har1r5"]["decision_state"],
        "active_g1_state": timeline["active_g1"]["decision_state"],
        "february_state": timeline["february_historical_diagnostic"]["decision_state"],
        "february_guard_status": timeline["february_historical_diagnostic"]["guard_status"],
        "rsi_current_route_status": lineage["current_route_status"],
        "rsi_v0_2_2_reproducible": True,
        "python_requires": runtime["python_requires"],
        "paper_only": True,
        "live_trading_authorized": False,
    }


@dataclass(frozen=True)
class CurrentSystemStatus:
    path: Path
    raw: dict[str, Any]
    summary: dict[str, Any]

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        workspace_root: Path | None = None,
    ) -> "CurrentSystemStatus":
        status_path = Path(path)
        try:
            raw_bytes = status_path.read_bytes()
        except OSError as exc:
            raise CurrentSystemStatusError("cannot read current system status") from exc
        raw = _load_json_bytes(raw_bytes, "current system status")
        root = Path(workspace_root).resolve() if workspace_root is not None else status_path.resolve().parent.parent
        summary = validate_current_system_status(raw, root)
        return cls(path=status_path.resolve(), raw=raw, summary=summary)
