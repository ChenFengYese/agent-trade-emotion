from __future__ import annotations

from datetime import UTC, datetime
import json
import unittest

from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    ObservationMissingness,
    ObservationQuality,
    build_minimal_experiment_contract,
    build_typed_path_monitor_plan,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.v31_public_outcome_adapter import (
    ABSOLUTE_MARK_OBSERVABLE,
    OKX_MARK_PRICE_URL,
    OkxPublicMarkPriceOutcomeAdapter,
    V31PublicOutcomeAdapterError,
)


class _Transport:
    def __init__(self, body: bytes, *, final_url: str = OKX_MARK_PRICE_URL) -> None:
        self.body = body
        self.final_url = final_url
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.calls += 1
        if url != OKX_MARK_PRICE_URL or timeout != 15.0:
            raise AssertionError("unexpected public request")
        return HttpCapture(
            status=200,
            headers={"Content-Type": "application/json"},
            body=self.body,
            received_at=datetime(2026, 8, 6, 11, 0, 5, tzinfo=UTC),
            final_url=self.final_url,
        )


def _plan() -> dict:
    contract = build_minimal_experiment_contract(
        contract_id="contract:v31:outcome-adapter",
        run_id="run:v31:outcome-adapter",
        frozen_at="2026-08-06T09:00:00Z",
    )
    origins = {
        "accepted_state": {"ref": "cycles/0001/accepted-research-state.json", "digest": "a" * 64},
        "path_set": {"ref": "path-set:1", "digest": "b" * 64},
        "path": {"ref": "path:lead:1", "digest": "c" * 64},
        "hypothesis_revision": {"ref": "hypothesis:lead:r1", "digest": "d" * 64},
        "expectation_revision": {"ref": "expectation:lead:r1", "digest": "e" * 64},
    }
    rules = (
        FrozenMonitorRule(
            rule_id="confirmation",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=ABSOLUTE_MARK_OBSERVABLE,
            operator=MonitorOperator.GT,
            expected="65000",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="contradiction",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=ABSOLUTE_MARK_OBSERVABLE,
            operator=MonitorOperator.LT,
            expected="64000",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="falsifier",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=ABSOLUTE_MARK_OBSERVABLE,
            operator=MonitorOperator.LTE,
            expected="63000",
            unit="USDT_PER_BTC",
        ),
    )
    return build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id="monitor:1",
        cycle_id="cycle:1",
        cycle_index=1,
        origin_bindings=origins,
        decision_at="2026-08-06T10:00:00Z",
        observable_ref=ABSOLUTE_MARK_OBSERVABLE,
        source_request_id="okx-public-mark-price:1",
        rules=rules,
    )


class V31PublicOutcomeAdapterTests(unittest.TestCase):
    def test_exact_public_mark_response_becomes_observed_absolute_mark(self) -> None:
        raw = json.dumps(
            {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "instType": "SWAP",
                        "instId": "BTC-USDT-SWAP",
                        "markPx": "64677.6",
                        "ts": "1786014004000",
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        transport = _Transport(raw)
        reading = OkxPublicMarkPriceOutcomeAdapter(
            transport=transport
        ).observe_public_outcome(
            monitor_plan=_plan(), requested_at="2026-08-06T11:00:00Z"
        )
        self.assertEqual(1, transport.calls)
        self.assertEqual("64677.6", reading.value)
        self.assertEqual(ObservationMissingness.OBSERVED, reading.missingness)
        self.assertEqual(ObservationQuality.HIGH, reading.quality)
        self.assertEqual("1", reading.coverage)
        self.assertEqual(raw, reading.raw_payload)
        self.assertEqual(OKX_MARK_PRICE_URL, reading.source_locator)

    def test_provider_empty_data_is_retained_as_unknown_not_zero(self) -> None:
        raw = b'{"code":"0","msg":"","data":[]}'
        reading = OkxPublicMarkPriceOutcomeAdapter(
            transport=_Transport(raw)
        ).observe_public_outcome(
            monitor_plan=_plan(), requested_at="2026-08-06T11:00:00Z"
        )
        self.assertIsNone(reading.value)
        self.assertEqual(ObservationMissingness.UNKNOWN, reading.missingness)
        self.assertEqual(ObservationQuality.UNKNOWN, reading.quality)
        self.assertEqual("0", reading.coverage)
        self.assertEqual(raw, reading.raw_payload)

    def test_wrong_observable_redirect_and_early_request_fail_before_admission(self) -> None:
        plan = _plan()
        plan["observable"]["observable_ref"] = "metric:mark-price-change-at-1h"
        transport = _Transport(b"{}")
        with self.assertRaisesRegex(
            V31PublicOutcomeAdapterError, "V31_OUTCOME_PLAN_SCOPE_INVALID"
        ):
            OkxPublicMarkPriceOutcomeAdapter(
                transport=transport
            ).observe_public_outcome(
                monitor_plan=plan, requested_at="2026-08-06T11:00:00Z"
            )
        self.assertEqual(0, transport.calls)

        with self.assertRaisesRegex(
            V31PublicOutcomeAdapterError, "V31_OUTCOME_REQUEST_NOT_DUE"
        ):
            OkxPublicMarkPriceOutcomeAdapter(
                transport=_Transport(b"{}")
            ).observe_public_outcome(
                monitor_plan=_plan(), requested_at="2026-08-06T10:59:59Z"
            )

        with self.assertRaisesRegex(
            V31PublicOutcomeAdapterError, "V31_OUTCOME_PUBLIC_RESPONSE_INVALID"
        ):
            OkxPublicMarkPriceOutcomeAdapter(
                transport=_Transport(b"{}", final_url="https://example.com/")
            ).observe_public_outcome(
                monitor_plan=_plan(), requested_at="2026-08-06T11:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
