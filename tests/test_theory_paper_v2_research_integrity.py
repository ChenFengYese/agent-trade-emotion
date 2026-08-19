from __future__ import annotations

import hashlib
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from trade_system.theory_paper_v2.application.continuous_cycle import (
    ContinuousResearchCycleCoordinator,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.portfolio_truth import (
    build_lot_position_truth,
)
from trade_system.theory_paper_v2.domain.research_integrity import (
    ACTION_CLASSES,
    ResearchIntegrityError,
    build_action_evaluation_set,
    build_four_cycle_review,
    make_agent_invocation_receipt,
    reduce_path_beliefs,
    select_from_evaluation_set,
)
from trade_system.theory_paper_v2.infrastructure.research_cycle_store import (
    EVENT_ACTORS,
    EVENT_ARTIFACT_BINDINGS,
    PRE_EVIDENCE_RECEIPT_EVENT_TYPES,
    PRE_COMPLETION_EVENT_TYPES,
    REQUIRED_ARTIFACT_BINDINGS,
    REQUIRED_EVIDENCE_ARTIFACT_BINDINGS,
    ResearchCycleStore,
    ResearchCycleStoreError,
)
from trade_system.theory_paper_v2.presentation.continuous_cycle_report import (
    CycleReportError,
    REQUIRED_SUMMARY_FIELDS,
    render_cycle_user_summary,
)


def belief_event(
    event_id: str,
    operation: str,
    path_id: str,
    evidence_id: str,
    *,
    lineage: str = "price:1h",
    direction: str | None = "SUPPORT",
    strength: int | None = 2,
    supersedes: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "operation": operation,
        "path_id": path_id,
        "evidence_id": evidence_id,
        "lineage_key": lineage,
        "direction": direction,
        "strength": strength,
        "available_at": "2026-08-05T10:00:00Z",
        "source_ref": None if operation == "EXPIRE" else f"source:{event_id}",
        "premise_ref": None if operation == "EXPIRE" else f"premise:{path_id}",
        "supersedes_evidence_id": supersedes,
    }


def path_outcomes(prefix: str, *, position_truth_digest: str) -> list[dict]:
    return [
        {
            "path_id": "path:trend",
            "source_cycle_index": 4,
            "position_truth_digest": position_truth_digest,
            "process_id": f"{prefix}:continuation",
            "distinguishing_evidence_refs": ["ev:trend"],
            "failure_trigger_refs": ["trigger:trend-break"],
            "position_consequence": "retains upside participation",
            "compatibility": "FAVORS_EXPOSURE",
            "market_process": "higher-timeframe demand persists through a shallow pullback",
            "failure_process": "failed reclaim converts continuation into distribution",
            "opportunity_cost": "underexposure loses the continuation leg",
            "cost_risk_tradeoff": "incremental exposure pays cost and carries stop-defined loss",
        },
        {
            "path_id": "path:pullback",
            "source_cycle_index": 4,
            "position_truth_digest": position_truth_digest,
            "process_id": f"{prefix}:pullback",
            "distinguishing_evidence_refs": ["ev:pullback"],
            "failure_trigger_refs": ["trigger:pullback-deepens"],
            "position_consequence": "keeps strategic exposure while tactical heat cools",
            "compatibility": "CONDITIONAL",
            "market_process": "short-horizon supply mean-reverts inside an intact 4h structure",
            "failure_process": "loss of the defended structure turns a pullback into failure",
            "opportunity_cost": "excess size absorbs avoidable drawdown",
            "cost_risk_tradeoff": "partial reduction trades some rebound capture for lower tail loss",
        },
        {
            "path_id": "path:other",
            "source_cycle_index": 4,
            "position_truth_digest": position_truth_digest,
            "process_id": f"{prefix}:residual",
            "distinguishing_evidence_refs": ["ev:other"],
            "failure_trigger_refs": ["trigger:unknown-expands"],
            "position_consequence": "leaves residual model error explicitly priced",
            "compatibility": "UNCERTAIN",
            "market_process": "unobserved event or liquidity mechanism dominates current signals",
            "failure_process": "known path evidence stops discriminating the realized move",
            "opportunity_cost": "waiting or exposure can both be wrong under residual uncertainty",
            "cost_risk_tradeoff": "hard risk limits bound the unknown branch without calling it neutral",
        },
    ]


def candidate(
    candidate_id: str,
    action_class: str,
    sizing_id: str,
    delta: str,
    *,
    stop: str | None = "90",
) -> dict:
    target_ids = (
        []
        if action_class in {"OPEN", "REENTER"}
        else ["lot:SNDKUSDT:core"]
    )
    truth_digest = build_lot_position_truth(
        symbol="SNDKUSDT", position_truth=portfolio_truth()
    )["position_truth_digest"]
    return {
        "candidate_id": candidate_id,
        "source_cycle_index": 4,
        "action_class": action_class,
        "sizing_id": sizing_id,
        "quantity_delta": delta,
        "stop_price_after": (
            None if action_class in {"HOLD", "WAIT", "EXIT"} else stop
        ),
        "target_lot_ids": target_ids,
        "target_lot_role": "CORE",
        "thesis_path_id": "path:trend",
        "evidence_refs": ["ev:trend", "ev:pullback"],
        "rationale": f"evaluate {action_class} at {sizing_id} against all three paths",
        "path_outcomes": path_outcomes(
            candidate_id, position_truth_digest=truth_digest
        ),
        "wait_until": "2026-08-05T12:00:00Z" if action_class == "WAIT" else None,
        "wait_for_observations": (
            ["observe:next-closed-15m-bar"] if action_class == "WAIT" else []
        ),
    }


def portfolio_truth(
    *,
    symbol: str = "SNDKUSDT",
    mark: str = "100",
    quantity: str = "1",
    stop: str = "90",
    portfolio_gross: str = "500",
    portfolio_risk: str = "50",
) -> dict:
    mark_value = Decimal(mark)
    quantity_value = Decimal(quantity)
    stop_value = Decimal(stop)
    gross_value = Decimal(portfolio_gross)
    risk_value = Decimal(portfolio_risk)
    target_notional = quantity_value * mark_value
    target_risk = quantity_value * abs(mark_value - stop_value)
    ballast_notional = gross_value - target_notional
    ballast_risk = risk_value - target_risk
    if ballast_notional <= 0 or ballast_risk < 0:
        raise AssertionError("test portfolio ballast must remain positive")
    ballast_stop = Decimal("1") - ballast_risk / ballast_notional
    target_margin = target_notional * Decimal("0.5")
    ballast_margin = ballast_notional * Decimal("0.5")
    margin_used = target_margin + ballast_margin
    return {
        "intended_side": "LONG",
        "mark_price": mark,
        "contract_multiplier": "1",
        "reentry_contract_active": False,
        "account": {
            "equity_usdt": "10000",
            "margin_used_usdt": str(margin_used),
            "margin_available_usdt": str(Decimal("10000") - margin_used),
            "max_gross_leverage": "2",
        },
        "lots": [
            {
                "lot_id": f"lot:{symbol}:core",
                "symbol": symbol,
                "side": "LONG",
                "role": "CORE",
                "quantity": quantity,
                "entry_price": mark,
                "mark_price": mark,
                "stop_price": stop,
                "contract_multiplier": "1",
                "margin_used_usdt": str(target_margin),
            },
            {
                "lot_id": "lot:OTHERUSDT:core",
                "symbol": "OTHERUSDT",
                "side": "LONG",
                "role": "CORE",
                "quantity": str(ballast_notional),
                "entry_price": "1",
                "mark_price": "1",
                "stop_price": str(ballast_stop),
                "contract_multiplier": "1",
                "margin_used_usdt": str(ballast_margin),
            },
        ],
        "pending_orders": [],
    }


def risk_policy() -> dict:
    return {
        "fee_rate": "0.0005",
        "slippage_rate": "0.001",
        "initial_margin_rate": "0.5",
        "max_gross_leverage": "2",
        "portfolio_risk_cap_usdt": "300",
        "symbol_risk_cap_usdt": "100",
        "gross_notional_cap_usdt": "2000",
        "symbol_notional_cap_usdt": "1000",
    }


def candidates() -> list[dict]:
    return [
        candidate("hold", "HOLD", "HOLD_CURRENT", "0"),
        candidate("open", "OPEN", "OPEN_PROBE", "0.1"),
        candidate("add", "ADD", "ADD_PROBE", "0.1"),
        candidate("reduce25", "REDUCE", "REDUCE_25", "-0.25"),
        candidate("reduce50", "REDUCE", "REDUCE_50", "-0.5"),
        candidate("reduce75", "REDUCE", "REDUCE_75", "-0.75"),
        candidate("partial", "PARTIAL_TAKE_PROFIT", "PARTIAL_25", "-0.25"),
        candidate("exit", "EXIT", "EXIT_100", "-1", stop=None),
        candidate("reenter", "REENTER", "REENTER_PROBE", "0.1"),
        candidate("wait", "WAIT", "WAIT_REVIEW", "0"),
    ]


def evaluation_set(
    symbol: str = "SNDKUSDT", candidate_rows: list[dict] | None = None
) -> dict:
    return build_action_evaluation_set(
        run_id="research-run",
        cycle_index=4,
        decision_at="2026-08-05T11:17:50Z",
        symbol=symbol,
        belief_state_digest="a" * 64,
        operational_lead_path_id="path:trend",
        runner_up_path_id="path:pullback",
        residual_path_id="path:other",
        position_truth=portfolio_truth(symbol=symbol),
        risk_policy=risk_policy(),
        valid_evidence_refs=("ev:trend", "ev:pullback", "ev:other"),
        valid_failure_trigger_refs=(
            "trigger:trend-break",
            "trigger:pullback-deepens",
            "trigger:unknown-expands",
        ),
        required_sizing_ids=("REDUCE_25", "REDUCE_50", "REDUCE_75", "EXIT_100"),
        candidate_proposals=candidates() if candidate_rows is None else candidate_rows,
    )


def actual_cycle4_evaluation(symbol: str) -> dict:
    facts = {
        "SNDKUSDT": {
            "mark": "1404.47",
            "quantity": "0.3474949091995802261496869071",
            "stop": "1380.99205768",
            "symbol_risk": "8.542303619276011036438316179",
            "evidence": (
                "SNDKUSDT:1h:change_1_bar_pct",
                "SNDKUSDT:15m:trend_state",
                "SNDKUSDT:leverage:open_interest_value_1h_change_pct",
            ),
            "lead": "一小时和十五分钟失速且 OI 一小时收缩，失败路径获得直接前缀",
            "runner": "四小时结构仍向上，浅回撤后恢复仍是独立竞争过程",
        },
        "ETHUSDT": {
            "mark": "1867.39",
            "quantity": "0.4024015323450351698939269561",
            "stop": "1842.95633828",
            "symbol_risk": "10.42531843931513593123762615",
            "evidence": (
                "ETHUSDT:1h:bollinger_percent_b",
                "ETHUSDT:flow:hourly_taker_buy_sell_ratio",
                "ETHUSDT:leverage:open_interest_value_1h_change_pct",
            ),
            "lead": "四小时区间与一小时 VWAP 下方运行使区间重组成为首要过程",
            "runner": "小时卖方流和 OI 收缩使区间下破失败路径保持竞争",
        },
    }[symbol]
    quantity = Decimal(facts["quantity"])
    specifications = (
        ("hold", "HOLD", "HOLD_CURRENT", Decimal("0")),
        ("open", "OPEN", "OPEN_PROBE", quantity * Decimal("0.1")),
        ("add", "ADD", "ADD_PROBE", quantity * Decimal("0.1")),
        ("reduce25", "REDUCE", "REDUCE_25", -quantity * Decimal("0.25")),
        ("reduce50", "REDUCE", "REDUCE_50", -quantity * Decimal("0.5")),
        ("reduce75", "REDUCE", "REDUCE_75", -quantity * Decimal("0.75")),
        ("partial", "PARTIAL_TAKE_PROFIT", "PARTIAL_25", -quantity * Decimal("0.25")),
        ("exit", "EXIT", "EXIT_100", -quantity),
        ("reenter", "REENTER", "REENTER_PROBE", quantity * Decimal("0.1")),
        ("wait", "WAIT", "WAIT_REVIEW", Decimal("0")),
    )
    truth_input = portfolio_truth(
        symbol=symbol,
        mark=facts["mark"],
        quantity=facts["quantity"],
        stop=facts["stop"],
        portfolio_gross="3728.793249938890187783010549",
        portfolio_risk="64.82756294319230385598988562",
    )
    truth_digest = build_lot_position_truth(
        symbol=symbol, position_truth=truth_input
    )["position_truth_digest"]
    rows = []
    for candidate_id, action_class, sizing_id, delta in specifications:
        rows.append(
            {
                "candidate_id": f"{symbol}:{candidate_id}",
                "source_cycle_index": 4,
                "action_class": action_class,
                "sizing_id": sizing_id,
                "quantity_delta": str(delta),
                "stop_price_after": (
                    None
                    if action_class in {"HOLD", "WAIT", "EXIT"}
                    else facts["stop"]
                ),
                "target_lot_ids": (
                    []
                    if action_class in {"OPEN", "REENTER"}
                    else [f"lot:{symbol}:core"]
                ),
                "target_lot_role": "CORE",
                "thesis_path_id": "path:lead",
                "evidence_refs": list(facts["evidence"][:2]),
                "rationale": f"{symbol} 用本轮真实仓位比较 {sizing_id}",
                "wait_until": (
                    "2026-08-05T12:17:50.781Z" if action_class == "WAIT" else None
                ),
                "wait_for_observations": (
                    [f"{symbol}:next-closed-15m-bar"]
                    if action_class == "WAIT"
                    else []
                ),
                "path_outcomes": [
                    {
                        "path_id": "path:lead",
                        "source_cycle_index": 4,
                        "position_truth_digest": truth_digest,
                        "process_id": f"{symbol}:{candidate_id}:lead",
                        "distinguishing_evidence_refs": [facts["evidence"][0]],
                        "failure_trigger_refs": [f"{symbol}:lead-fails"],
                        "position_consequence": "按所选尺度改变当前核心暴露",
                        "compatibility": "LEAD_PATH_DEPENDENT",
                        "market_process": facts["lead"],
                        "failure_process": "lead 的关键结构观测反转后，该动作失去当前依据",
                        "opportunity_cost": "尺度过小或过大分别损失保护或路径参与",
                        "cost_risk_tradeoff": "使用真实 lot 数量、费用、stop 和剩余风险计算",
                    },
                    {
                        "path_id": "path:runner",
                        "source_cycle_index": 4,
                        "position_truth_digest": truth_digest,
                        "process_id": f"{symbol}:{candidate_id}:runner",
                        "distinguishing_evidence_refs": [facts["evidence"][1]],
                        "failure_trigger_refs": [f"{symbol}:runner-fails"],
                        "position_consequence": "保留 runner-up 兑现时的可恢复暴露",
                        "compatibility": "RUNNER_PATH_DEPENDENT",
                        "market_process": facts["runner"],
                        "failure_process": "runner 的结构恢复条件没有出现",
                        "opportunity_cost": "忽略 runner 会造成过度减仓或过早加仓",
                        "cost_risk_tradeoff": "相邻尺度用同一执行成本和风险上限比较",
                    },
                    {
                        "path_id": "path:other",
                        "source_cycle_index": 4,
                        "position_truth_digest": truth_digest,
                        "process_id": f"{symbol}:{candidate_id}:other",
                        "distinguishing_evidence_refs": [facts["evidence"][2]],
                        "failure_trigger_refs": [f"{symbol}:unknown-expands"],
                        "position_consequence": "保留 residual model error 的显式损失上限",
                        "compatibility": "RESIDUAL_UNCERTAINTY",
                        "market_process": "未观测事件或流动性机制主导当前信号",
                        "failure_process": "已知路径失去区分能力",
                        "opportunity_cost": "空仓与持仓都存在非零机会成本",
                        "cost_risk_tradeoff": "只用硬风险限制未知，不把未知补成零",
                    },
                ],
            }
        )
    return build_action_evaluation_set(
        run_id="single-agent-prospective-24h-v14-20260805t074500z",
        cycle_index=4,
        decision_at="2026-08-05T11:17:50.781Z",
        symbol=symbol,
        belief_state_digest="a" * 64,
        operational_lead_path_id="path:lead",
        runner_up_path_id="path:runner",
        residual_path_id="path:other",
        position_truth=truth_input,
        risk_policy={
            "fee_rate": "0.0005",
            "slippage_rate": "0.001",
            "initial_margin_rate": "0.5",
            "max_gross_leverage": "2",
            "portfolio_risk_cap_usdt": "297.2384229803607176177045565",
            "symbol_risk_cap_usdt": "99.07947432678690587256818551",
            "gross_notional_cap_usdt": "10000",
            "symbol_notional_cap_usdt": "2000",
        },
        valid_evidence_refs=facts["evidence"],
        valid_failure_trigger_refs=(
            f"{symbol}:lead-fails",
            f"{symbol}:runner-fails",
            f"{symbol}:unknown-expands",
        ),
        required_sizing_ids=("REDUCE_25", "REDUCE_50", "REDUCE_75", "EXIT_100"),
        candidate_proposals=rows,
    )


class ResearchIntegrityTests(unittest.TestCase):
    def test_belief_state_persists_and_only_explicit_events_change_it(self) -> None:
        paths = ("path:trend", "path:pullback", "path:other")
        first = reduce_path_beliefs(
            previous_state=None,
            belief_events=(
                belief_event("event:1", "ADD", "path:trend", "evidence:trend", strength=3),
                belief_event(
                    "event:2",
                    "ADD",
                    "path:trend",
                    "evidence:flow",
                    lineage="flow:1h",
                    strength=2,
                ),
            ),
            path_ids=paths,
            decision_at="2026-08-05T11:00:00Z",
        )
        self.assertEqual("DOMINANT", first["path_beliefs"]["path:trend"]["support_level"])
        silent = reduce_path_beliefs(
            previous_state=first,
            belief_events=(),
            path_ids=paths,
            decision_at="2026-08-05T12:00:00Z",
        )
        self.assertEqual(5, silent["path_beliefs"]["path:trend"]["ordinal_balance"])
        self.assertEqual(
            first["path_beliefs"]["path:trend"]["support_level"],
            silent["path_beliefs"]["path:trend"]["support_level"],
        )
        challenged = reduce_path_beliefs(
            previous_state=silent,
            belief_events=(
                belief_event(
                    "event:3",
                    "SUPERSEDE",
                    "path:trend",
                    "evidence:trend-new",
                    strength=1,
                    supersedes="evidence:trend",
                ),
                belief_event(
                    "event:4",
                    "SOFT_CONTRADICTION",
                    "path:trend",
                    "evidence:supply",
                    lineage="supply:15m",
                    direction="SOFT_CONTRADICTION",
                    strength=2,
                ),
            ),
            path_ids=paths,
            decision_at="2026-08-05T13:00:00Z",
        )
        self.assertEqual(1, challenged["path_beliefs"]["path:trend"]["ordinal_balance"])
        self.assertEqual("PLAUSIBLE", challenged["path_beliefs"]["path:trend"]["support_level"])
        replay = reduce_path_beliefs(
            previous_state=silent,
            belief_events=(
                belief_event(
                    "event:3",
                    "SUPERSEDE",
                    "path:trend",
                    "evidence:trend-new",
                    strength=1,
                    supersedes="evidence:trend",
                ),
                belief_event(
                    "event:4",
                    "SOFT_CONTRADICTION",
                    "path:trend",
                    "evidence:supply",
                    lineage="supply:15m",
                    direction="SOFT_CONTRADICTION",
                    strength=2,
                ),
            ),
            path_ids=paths,
            decision_at="2026-08-05T13:00:00Z",
        )
        self.assertEqual(challenged["belief_state_digest"], replay["belief_state_digest"])

    def test_hard_falsifier_is_reducer_owned(self) -> None:
        state = reduce_path_beliefs(
            previous_state=None,
            belief_events=(
                belief_event(
                    "event:hard",
                    "HARD_FALSIFIER",
                    "path:trend",
                    "evidence:hard",
                    direction="HARD_FALSIFIER",
                    strength=3,
                ),
            ),
            path_ids=("path:trend",),
            decision_at="2026-08-05T11:00:00Z",
        )
        self.assertEqual("INVALIDATED", state["path_beliefs"]["path:trend"]["support_level"])

    def test_evaluation_is_sealed_before_selection_and_uses_real_sizes(self) -> None:
        sealed = evaluation_set()
        by_id = {row["candidate_id"]: row for row in sealed["candidates"]}
        self.assertEqual(ACTION_CLASSES, {row["action_class"] for row in by_id.values()})
        self.assertEqual("0.75", by_id["reduce25"]["economics"]["quantity_after"])
        self.assertEqual("0.25", by_id["reduce75"]["economics"]["quantity_after"])
        self.assertFalse(by_id["open"]["feasible"])
        digest_before = sealed["action_evaluation_digest"]
        feasible = [
            row["candidate_id"]
            for row in sealed["candidates"]
            if row["feasible"] and row["candidate_id"] != "reduce25"
        ]
        selection = select_from_evaluation_set(
            evaluation_set=sealed,
            selected_candidate_id="reduce25",
            ranked_alternative_ids=feasible,
            why_not_selected={item: f"reduce25 dominates {item} under current path tradeoff" for item in feasible},
            selection_rationale="retain core participation while reducing exhaustion exposure",
            agent_proposal_digest="b" * 64,
        )
        self.assertEqual(digest_before, selection["action_evaluation_digest"])
        self.assertEqual(digest_before, sealed["action_evaluation_digest"])

    def test_selected_field_cannot_enter_evaluation_phase(self) -> None:
        rows = candidates()
        rows[0] = {**rows[0], "selected_candidate_id": "hold"}
        with self.assertRaisesRegex(
            ResearchIntegrityError, "SELECTION_FIELD_FORBIDDEN"
        ):
            build_action_evaluation_set(
                run_id="research-run",
                cycle_index=4,
                decision_at="2026-08-05T11:17:50Z",
                symbol="SNDKUSDT",
                belief_state_digest="a" * 64,
                operational_lead_path_id="path:trend",
                runner_up_path_id="path:pullback",
                residual_path_id="path:other",
                position_truth=portfolio_truth(),
                risk_policy=risk_policy(),
                valid_evidence_refs=("ev:trend", "ev:pullback", "ev:other"),
                valid_failure_trigger_refs=(
                    "trigger:trend-break",
                    "trigger:pullback-deepens",
                    "trigger:unknown-expands",
                ),
                required_sizing_ids=("REDUCE_25", "REDUCE_50", "REDUCE_75", "EXIT_100"),
                candidate_proposals=rows,
            )

    def test_failure_triggers_wait_obligation_and_size_are_registered(self) -> None:
        unknown_trigger = candidates()
        unknown_trigger[0]["path_outcomes"][0]["failure_trigger_refs"] = [
            "trigger:invented"
        ]
        with self.assertRaisesRegex(
            ResearchIntegrityError, "ACTION_PATH_OUTCOME_INVALID"
        ):
            build_action_evaluation_set(
                run_id="research-run",
                cycle_index=4,
                decision_at="2026-08-05T11:17:50Z",
                symbol="SNDKUSDT",
                belief_state_digest="a" * 64,
                operational_lead_path_id="path:trend",
                runner_up_path_id="path:pullback",
                residual_path_id="path:other",
                position_truth=portfolio_truth(),
                risk_policy=risk_policy(),
                valid_evidence_refs=("ev:trend", "ev:pullback", "ev:other"),
                valid_failure_trigger_refs=(
                    "trigger:trend-break",
                    "trigger:pullback-deepens",
                    "trigger:unknown-expands",
                ),
                required_sizing_ids=(
                    "REDUCE_25",
                    "REDUCE_50",
                    "REDUCE_75",
                    "EXIT_100",
                ),
                candidate_proposals=unknown_trigger,
            )

        missing_wait = candidates()
        missing_wait[-1]["wait_for_observations"] = []
        with self.assertRaisesRegex(
            ResearchIntegrityError, "ACTION_WAIT_OBLIGATION_INCOMPLETE"
        ):
            evaluation_set(candidate_rows=missing_wait)

        wrong_size = candidates()
        wrong_size[3]["quantity_delta"] = "-0.1"
        with self.assertRaisesRegex(
            ResearchIntegrityError, "ACTION_SIZING_QUANTITY_MISMATCH"
        ):
            evaluation_set(candidate_rows=wrong_size)

    def test_platform_receipt_digest_does_not_overclaim_model_attestation(self) -> None:
        with self.assertRaisesRegex(
            ResearchIntegrityError, "PLATFORM_MODEL_RECEIPT_DIGEST_INVALID"
        ):
            make_agent_invocation_receipt(
                run_id="run",
                cycle_index=1,
                attempt_id="attempt-1",
                input_context_digest="a" * 64,
                proposal_digest="b" * 64,
                started_at="2026-08-05T11:00:00Z",
                ended_at="2026-08-05T11:01:00Z",
                automation_id=None,
                thread_id=None,
                platform_model_receipt="unverified string",
            )
        receipt = make_agent_invocation_receipt(
            run_id="run",
            cycle_index=1,
            attempt_id="attempt-1",
            input_context_digest="a" * 64,
            proposal_digest="b" * 64,
            started_at="2026-08-05T11:00:00Z",
            ended_at="2026-08-05T11:01:00Z",
            automation_id=None,
            thread_id=None,
            platform_model_receipt="c" * 64,
        )
        self.assertEqual(
            "PLATFORM_RECEIPT_DIGEST_BOUND_IDENTITY_SCOPE_UNVERIFIED",
            receipt["model_identity_evidence"],
        )

    def test_non_template_multisymbol_evaluations_remain_symbol_specific(self) -> None:
        sndk = actual_cycle4_evaluation("SNDKUSDT")
        eth = actual_cycle4_evaluation("ETHUSDT")
        self.assertNotEqual(sndk["action_evaluation_digest"], eth["action_evaluation_digest"])
        self.assertEqual("SNDKUSDT", sndk["symbol"])
        self.assertEqual("ETHUSDT", eth["symbol"])
        sndk_process = sndk["candidates"][0]["path_outcomes"][0]["market_process"]
        eth_process = eth["candidates"][0]["path_outcomes"][0]["market_process"]
        self.assertIn("OI", sndk_process)
        self.assertIn("VWAP", eth_process)
        self.assertNotEqual(sndk_process, eth_process)

    def test_four_cycle_review_computes_all_required_metrics(self) -> None:
        rows = []
        for cycle in range(1, 5):
            rows.append(
                {
                    "cycle_index": cycle,
                    "lead_path_id": f"path:{cycle}",
                    "lead_prefix_status": "SUPPORTED" if cycle < 4 else "UNRESOLVED",
                    "selected_candidate_id": f"candidate:{cycle}",
                    "applied_candidate_id": f"candidate:{cycle}",
                    "agent_net_pnl_usdt": str(-cycle),
                    "baseline_net_pnl_usdt": str(-cycle - 1),
                    "available_favorable_move_usdt": "10",
                    "captured_favorable_move_usdt": "5",
                    "available_add_risk_usdt": "20",
                    "deployed_add_risk_usdt": "5",
                    "reentry_status": "NOT_APPLICABLE",
                    "eligible_reentry_at": None,
                    "reentered_at": None,
                    "fees_usdt": "0.5",
                    "funding_status": "UNKNOWN",
                    "funding_usdt": None,
                    "equity_usdt": str(100 - cycle),
                    "peak_equity_usdt": "100",
                }
            )
        review = build_four_cycle_review(
            run_id="run", through_cycle=4, cycle_rows=rows
        )
        self.assertEqual(4, review["summary"]["action_fidelity_count"])
        self.assertEqual("0.5", review["summary"]["mean_known_path_capture_ratio"])
        broken = dict(rows[0])
        broken.pop("fees_usdt")
        with self.assertRaisesRegex(
            ResearchIntegrityError, "FOUR_CYCLE_REVIEW_FIELDS_INCOMPLETE"
        ):
            build_four_cycle_review(
                run_id="run", through_cycle=4, cycle_rows=[broken, *rows[1:]]
            )


class ResearchCycleStoreTests(unittest.TestCase):
    @staticmethod
    def physical_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def fixtures(
        self, root: Path, *, cycle_index: int
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        bindings: dict[str, str] = {}
        refs: dict[str, str] = {}
        digests: dict[str, str] = {}
        fixture_event_types = PRE_EVIDENCE_RECEIPT_EVENT_TYPES + ("REPORT_SEALED",)
        for event_type in fixture_event_types:
            ref = (
                f"states/state-{cycle_index:04d}.json"
                if event_type == "STATE_ACCEPTED"
                else f"artifacts/cycle-{cycle_index:04d}/{event_type}.json"
            )
            path = root / ref
            write_once_json(
                path,
                {
                    "schema_id": "research_cycle_store_test_payload",
                    "cycle_index": cycle_index,
                    "event_type": event_type,
                },
            )
            digest = self.physical_sha256(path)
            refs[event_type] = ref
            digests[event_type] = digest
            artifact_name = EVENT_ARTIFACT_BINDINGS.get(event_type)
            if artifact_name is not None:
                bindings[artifact_name] = digest
        self.assertEqual(
            REQUIRED_EVIDENCE_ARTIFACT_BINDINGS | {"report_sha256"},
            set(bindings),
        )
        return bindings, refs, digests

    @staticmethod
    def append_events(
        store: ResearchCycleStore,
        event_types: tuple[str, ...],
        refs: dict[str, str],
        digests: dict[str, str],
        *,
        recorded_at: str,
    ) -> None:
        for event_type in event_types:
            store.append_event(
                event_type=event_type,
                payload_ref=refs[event_type],
                payload_digest=digests[event_type],
                actor=EVENT_ACTORS[event_type],
                recorded_at=recorded_at,
                evidence_boundary="TEST_PIT_BOUNDARY",
            )

    def test_completion_binds_report_comparator_review_then_advances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindings, refs, digests = self.fixtures(root, cycle_index=4)
            store = ResearchCycleStore(root, run_id="run", cycle_index=4)
            coordinator = ContinuousResearchCycleCoordinator(
                store, run_id="run", cycle_index=4
            )
            post_accept_boundary = (
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES.index("ACTION_RECEIPT_SEALED") + 1
            )
            self.append_events(
                store,
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES[:post_accept_boundary],
                refs,
                digests,
                recorded_at="2026-08-05T11:00:00Z",
            )
            checkpoint_path = root / "checkpoint.json"
            write_once_json(
                checkpoint_path,
                self_digest({
                    "run_id": "run",
                    "status": "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
                    "completed_cycles": 3,
                    "next_cycle_index": 4,
                }, "checkpoint_digest"),
            )
            coordinator.enter_post_accept_finalization(
                checkpoint_path=checkpoint_path,
                accepted_state_path=refs["STATE_ACCEPTED"],
                accepted_state_digest=bindings["accepted_state_digest"],
            )
            self.append_events(
                store,
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES[post_accept_boundary:],
                refs,
                digests,
                recorded_at="2026-08-05T11:01:00Z",
            )
            pre_evidence_recovery = coordinator.recovery_status()
            self.assertEqual(
                "CYCLE_EVIDENCE_RECEIPT_SEALED",
                pre_evidence_recovery["next_required_event_type"],
            )
            self.assertTrue(pre_evidence_recovery["agent_reinvocation_forbidden"])
            evidence = coordinator.seal_cycle_evidence(
                artifact_bindings={
                    key: value
                    for key, value in bindings.items()
                    if key in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
                },
                recorded_at="2026-08-05T11:01:30Z",
            )
            bindings["cycle_evidence_receipt_digest"] = evidence[
                "cycle_evidence_receipt_digest"
            ]
            self.append_events(
                store,
                ("REPORT_SEALED",),
                refs,
                digests,
                recorded_at="2026-08-05T11:01:45Z",
            )
            review_ref = "reviews/cycle-0004.json"
            write_once_json(
                root / review_ref,
                {"schema_id": "test_review", "through_cycle": 4},
            )
            review_digest = self.physical_sha256(root / review_ref)
            store.append_event(
                event_type="REVIEW_SEALED",
                payload_ref=review_ref,
                payload_digest=review_digest,
                actor=EVENT_ACTORS["REVIEW_SEALED"],
                recorded_at="2026-08-05T11:02:00Z",
                evidence_boundary="CYCLES_1_TO_4_ONLY",
            )
            result = coordinator.complete_cycle(
                checkpoint_path=checkpoint_path,
                artifact_bindings=bindings,
                accepted_state_path=refs["STATE_ACCEPTED"],
                recorded_at="2026-08-05T11:03:00Z",
                review_digest=review_digest,
            )
            self.assertEqual(4, result["checkpoint"]["completed_cycles"])
            self.assertEqual(5, result["checkpoint"]["next_cycle_index"])
            self.assertEqual("CYCLE_COMPLETED", store.read_events()[-1]["event_type"])
            retry = store.seal_completion(
                artifact_bindings=bindings,
                accepted_state_path=refs["STATE_ACCEPTED"],
                recorded_at="2026-08-05T11:04:00Z",
                review_digest=review_digest,
            )
            self.assertEqual(
                result["completion_receipt"]["completion_receipt_digest"],
                retry["completion_receipt_digest"],
            )
            recovery = coordinator.recovery_status()
            self.assertIsNone(recovery["next_required_event_type"])
            self.assertTrue(recovery["agent_reinvocation_forbidden"])

    def test_missing_report_binding_and_chain_break_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindings, refs, digests = self.fixtures(root, cycle_index=1)
            store = ResearchCycleStore(root, run_id="run", cycle_index=1)
            self.append_events(
                store,
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES,
                refs,
                digests,
                recorded_at="2026-08-05T11:00:00Z",
            )
            evidence = store.seal_evidence_receipt(
                artifact_bindings={
                    key: value
                    for key, value in bindings.items()
                    if key in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
                },
                recorded_at="2026-08-05T11:00:30Z",
            )
            bindings["cycle_evidence_receipt_digest"] = evidence[
                "cycle_evidence_receipt_digest"
            ]
            self.append_events(
                store,
                ("REPORT_SEALED",),
                refs,
                digests,
                recorded_at="2026-08-05T11:00:45Z",
            )
            missing = dict(bindings)
            missing.pop("report_sha256")
            with self.assertRaisesRegex(
                ResearchCycleStoreError, "CYCLE_COMPLETION_BINDINGS_INCOMPLETE"
            ):
                store.seal_completion(
                    artifact_bindings=missing,
                    accepted_state_path=refs["STATE_ACCEPTED"],
                    recorded_at="2026-08-05T11:01:00Z",
                    review_digest=None,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, refs, digests = self.fixtures(root, cycle_index=1)
            store = ResearchCycleStore(root, run_id="run", cycle_index=1)
            self.append_events(
                store,
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES[:2],
                refs,
                digests,
                recorded_at="2026-08-05T11:00:00Z",
            )
            first = sorted(store.events_root.glob("*.json"))[0]
            first.unlink()
            with self.assertRaisesRegex(
                ResearchCycleStoreError, "CYCLE_EVENT_CHAIN_BROKEN"
            ):
                store.read_events()

    def test_payload_actor_and_missing_decision_binding_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ResearchCycleStore(root, run_id="run", cycle_index=1)
            first_event_type = PRE_EVIDENCE_RECEIPT_EVENT_TYPES[0]
            with self.assertRaisesRegex(
                ResearchCycleStoreError, "CYCLE_EVENT_PAYLOAD_REF_INVALID"
            ):
                store.append_event(
                    event_type=first_event_type,
                    payload_ref="missing.json",
                    payload_digest="a" * 64,
                    actor=EVENT_ACTORS[first_event_type],
                    recorded_at="2026-08-05T11:00:00Z",
                    evidence_boundary="TEST",
                )

            bindings, refs, digests = self.fixtures(root, cycle_index=1)
            with self.assertRaisesRegex(
                ResearchCycleStoreError, "CYCLE_EVENT_FIELDS_INVALID"
            ):
                store.append_event(
                    event_type=first_event_type,
                    payload_ref=refs[first_event_type],
                    payload_digest=digests[first_event_type],
                    actor="UNREGISTERED_ACTOR",
                    recorded_at="2026-08-05T11:00:00Z",
                    evidence_boundary="TEST",
                )

            self.append_events(
                store,
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES,
                refs,
                digests,
                recorded_at="2026-08-05T11:00:00Z",
            )
            evidence = store.seal_evidence_receipt(
                artifact_bindings={
                    key: value
                    for key, value in bindings.items()
                    if key in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
                },
                recorded_at="2026-08-05T11:00:30Z",
            )
            bindings["cycle_evidence_receipt_digest"] = evidence[
                "cycle_evidence_receipt_digest"
            ]
            self.append_events(
                store,
                ("REPORT_SEALED",),
                refs,
                digests,
                recorded_at="2026-08-05T11:00:45Z",
            )
            wrong = dict(bindings)
            wrong["decision_digest"] = "f" * 64
            with self.assertRaisesRegex(
                ResearchCycleStoreError,
                "CYCLE_EVENT_ARTIFACT_BINDING_MISMATCH:decision_digest",
            ):
                store.seal_completion(
                    artifact_bindings=wrong,
                    accepted_state_path=refs["STATE_ACCEPTED"],
                    recorded_at="2026-08-05T11:01:00Z",
                    review_digest=None,
                )


class CycleSummaryTests(unittest.TestCase):
    def test_user_summary_cannot_collapse_to_one_line(self) -> None:
        summary = {
            field: [f"{field}: detailed evidence"]
            for field in REQUIRED_SUMMARY_FIELDS
        }
        summary["conclusion"] = "cycle completed with an explicit market decision"
        summary["current_status"] = "COMPLETED"
        summary["full_report_path"] = "reports/cycle-0001.md"
        summary["completion_receipt_digest"] = "a" * 64
        rendered = render_cycle_user_summary(summary)
        self.assertIn("### 数据采集与质量", rendered)
        self.assertIn("### 八类动作与仓位尺度比较", rendered)
        self.assertIn("### 仓位与交易", rendered)
        broken = dict(summary)
        broken.pop("path_updates")
        with self.assertRaisesRegex(CycleReportError, "INCOMPLETE"):
            render_cycle_user_summary(broken)


if __name__ == "__main__":
    unittest.main()
