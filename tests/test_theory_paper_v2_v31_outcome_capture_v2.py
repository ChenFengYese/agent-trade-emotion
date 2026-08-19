from __future__ import annotations

import copy
import json
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    CanonicalContractError,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    OutcomeCaptureParseStatus,
    OutcomeClockClass,
    V31OutcomeCaptureContractError,
    build_outcome_clock_policy,
    build_public_outcome_capture,
    build_public_outcome_transport_failure,
    parse_public_outcome_capture,
    verify_outcome_clock_policy,
    verify_public_outcome_capture,
    verify_public_outcome_parse_receipt,
    verify_public_outcome_transport_failure,
)


RECEIVED_AT = "2026-08-06T11:00:00Z"
RECEIVED_AT_MS = 1_786_014_000_000
OBSERVABLE = "metric:mark-price-usdt"


def raw_mark(*, timestamp_ms: int, mark: str = "64677.6000") -> bytes:
    return json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                    "markPx": mark,
                    "ts": str(timestamp_ms),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def capture(raw_payload: bytes, **overrides) -> dict:
    values = {
        "run_id": "run:v31:capture-v2",
        "cycle_index": 1,
        "monitor_plan_digest": "a" * 64,
        "monitor_attempt_digest": "b" * 64,
        "source_request_id": "okx-public-mark-price:1",
        "requested_at": "2026-08-06T10:59:59.900000Z",
        "request_started_at": "2026-08-06T10:59:59.950000Z",
        "response_received_at": RECEIVED_AT,
        "monotonic_elapsed_ms": 50,
        "status_code": 200,
        "content_type": "application/json; charset=utf-8",
        "final_url": OKX_MARK_PRICE_URL,
        "raw_payload": raw_payload,
    }
    values.update(overrides)
    return build_public_outcome_capture(**values)


class V31OutcomeCaptureV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = build_outcome_clock_policy()

    def parse(self, raw_payload: bytes, **capture_overrides) -> dict:
        captured = capture(raw_payload, **capture_overrides)
        return parse_public_outcome_capture(
            capture=captured,
            raw_payload=raw_payload,
            clock_policy=self.policy,
            observable_ref=OBSERVABLE,
        )

    def test_clock_policy_and_capture_are_exactly_reconstructible(self) -> None:
        self.assertEqual(
            self.policy["clock_policy_digest"],
            verify_outcome_clock_policy(self.policy),
        )
        raw = raw_mark(timestamp_ms=RECEIVED_AT_MS)
        captured = capture(raw)
        self.assertEqual(
            captured["capture_digest"],
            verify_public_outcome_capture(captured, raw_payload=raw),
        )
        self.assertEqual(len(raw), captured["raw_size_bytes"])
        with self.assertRaisesRegex(
            V31OutcomeCaptureContractError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_public_outcome_capture(captured, raw_payload=raw + b" ")

    def test_provider_clock_boundaries_are_exact_to_one_millisecond(self) -> None:
        cases = (
            (
                "exact",
                RECEIVED_AT_MS,
                OutcomeCaptureParseStatus.ADMITTED_OBSERVED,
                OutcomeClockClass.EXACT,
                "HIGH",
                "0",
            ),
            (
                "lead-at-bound",
                RECEIVED_AT_MS + 2_000,
                OutcomeCaptureParseStatus.ADMITTED_OBSERVED,
                OutcomeClockClass.PROVIDER_LEAD_WITHIN_BOUND,
                "MEDIUM",
                "2000",
            ),
            (
                "lead-one-ms-over",
                RECEIVED_AT_MS + 2_001,
                OutcomeCaptureParseStatus.ADMITTED_UNKNOWN,
                OutcomeClockClass.CLOCK_BOUND_EXCEEDED,
                "UNKNOWN",
                "2001",
            ),
            (
                "age-at-bound",
                RECEIVED_AT_MS - 5_000,
                OutcomeCaptureParseStatus.ADMITTED_OBSERVED,
                OutcomeClockClass.PROVIDER_LAG_WITHIN_BOUND,
                "HIGH",
                "-5000",
            ),
            (
                "age-one-ms-over",
                RECEIVED_AT_MS - 5_001,
                OutcomeCaptureParseStatus.ADMITTED_UNKNOWN,
                OutcomeClockClass.CLOCK_BOUND_EXCEEDED,
                "UNKNOWN",
                "-5001",
            ),
        )
        for name, timestamp, status, clock_class, quality, delta in cases:
            with self.subTest(name=name):
                receipt = self.parse(raw_mark(timestamp_ms=timestamp))
                self.assertEqual(status.value, receipt["parse_status"])
                self.assertEqual(clock_class.value, receipt["clock_class"])
                self.assertEqual(quality, receipt["quality"])
                self.assertEqual(delta, receipt["provider_clock_delta_ms"])

    def test_local_receive_is_evaluation_time_and_provider_time_is_unclamped(self) -> None:
        timestamp = RECEIVED_AT_MS + 2_000
        receipt = self.parse(raw_mark(timestamp_ms=timestamp))
        self.assertEqual(str(timestamp), receipt["provider_timestamp_raw"])
        self.assertEqual("2026-08-06T11:00:02.000Z", receipt["provider_as_of"])
        self.assertEqual(RECEIVED_AT, receipt["evaluation_as_of"])
        self.assertEqual(RECEIVED_AT, receipt["available_at"])
        self.assertEqual("64677.6", receipt["value"])

    def test_valid_but_out_of_bound_provider_time_becomes_unknown_not_zero(self) -> None:
        receipt = self.parse(raw_mark(timestamp_ms=RECEIVED_AT_MS + 2_001))
        self.assertEqual("ADMITTED_UNKNOWN", receipt["parse_status"])
        self.assertEqual("CLOCK_BOUND_EXCEEDED", receipt["error_code"])
        self.assertIsNone(receipt["value"])
        self.assertEqual("UNKNOWN", receipt["missingness"])
        self.assertEqual("0", receipt["coverage"])
        self.assertEqual("CLOCK_BOUND_EXCEEDED", receipt["conflict_state"])

    def test_provider_unavailable_and_empty_data_are_unknown(self) -> None:
        payloads = (
            (b'{"code":"50011","msg":"busy","data":[]}', "PROVIDER_REPORTED_UNAVAILABLE"),
            (b'{"code":"0","msg":"","data":[]}', "PROVIDER_DATA_EMPTY"),
        )
        for raw, code in payloads:
            with self.subTest(code=code):
                receipt = self.parse(raw)
                self.assertEqual("ADMITTED_UNKNOWN", receipt["parse_status"])
                self.assertEqual(code, receipt["error_code"])
                self.assertIsNone(receipt["value"])
                self.assertEqual("0", receipt["coverage"])

    def test_invalid_structure_time_and_value_are_rejected(self) -> None:
        wrong_instrument = raw_mark(timestamp_ms=RECEIVED_AT_MS).replace(
            b"BTC-USDT-SWAP", b"ETH-USDT-SWAP"
        )
        invalid_time = raw_mark(timestamp_ms=RECEIVED_AT_MS).replace(
            str(RECEIVED_AT_MS).encode(), b"not-a-time"
        )
        invalid_value = raw_mark(
            timestamp_ms=RECEIVED_AT_MS, mark="NaN"
        )
        duplicate_key = (
            b'{"code":"0","code":"0","msg":"","data":[]}'
        )
        cases = (
            (b"not-json", "PUBLIC_JSON_INVALID"),
            (duplicate_key, "PUBLIC_JSON_INVALID"),
            (wrong_instrument, "PUBLIC_INSTRUMENT_MISMATCH"),
            (invalid_time, "PUBLIC_TIME_INVALID"),
            (invalid_value, "PUBLIC_VALUE_INVALID"),
            (raw_mark(timestamp_ms=RECEIVED_AT_MS, mark="0"), "PUBLIC_VALUE_INVALID"),
        )
        for raw, code in cases:
            with self.subTest(code=code, raw=raw):
                receipt = self.parse(raw)
                self.assertEqual("REJECTED", receipt["parse_status"])
                self.assertEqual(code, receipt["error_code"])
                self.assertIsNone(receipt["value"])
                self.assertEqual("0", receipt["coverage"])

    def test_invalid_response_envelope_and_local_time_order_are_rejected(self) -> None:
        raw = raw_mark(timestamp_ms=RECEIVED_AT_MS)
        cases = (
            ({"status_code": 503}, "PUBLIC_STATUS_INVALID"),
            ({"content_type": "text/html"}, "PUBLIC_CONTENT_TYPE_INVALID"),
            ({"final_url": "https://example.com/"}, "PUBLIC_FINAL_URL_INVALID"),
            (
                {
                    "request_started_at": "2026-08-06T11:00:00.001000Z",
                    "response_received_at": RECEIVED_AT,
                },
                "CAPTURE_LOCAL_TIME_ORDER_INVALID",
            ),
        )
        for overrides, code in cases:
            with self.subTest(code=code):
                receipt = self.parse(raw, **overrides)
                self.assertEqual("REJECTED", receipt["parse_status"])
                self.assertEqual(code, receipt["error_code"])

    def test_parse_receipt_digest_is_rebuilt_from_exact_raw_capture_and_policy(self) -> None:
        raw = raw_mark(timestamp_ms=RECEIVED_AT_MS + 1_500)
        captured = capture(raw)
        receipt = parse_public_outcome_capture(
            capture=captured,
            raw_payload=raw,
            clock_policy=self.policy,
            observable_ref=OBSERVABLE,
        )
        self.assertEqual(
            receipt["parse_receipt_digest"],
            verify_public_outcome_parse_receipt(
                receipt,
                capture=captured,
                raw_payload=raw,
                clock_policy=self.policy,
                observable_ref=OBSERVABLE,
            ),
        )
        tampered = copy.deepcopy(receipt)
        tampered["evaluation_as_of"] = "2026-08-06T11:00:01Z"
        with self.assertRaisesRegex(
            (CanonicalContractError, V31OutcomeCaptureContractError),
            "DIGEST|RECONSTRUCTION",
        ):
            verify_public_outcome_parse_receipt(
                tampered,
                capture=captured,
                raw_payload=raw,
                clock_policy=self.policy,
                observable_ref=OBSERVABLE,
            )

    def test_typed_no_response_receipt_allows_only_abstract_failure_codes(self) -> None:
        receipt = build_public_outcome_transport_failure(
            run_id="run:v31:capture-v2",
            cycle_index=1,
            monitor_plan_digest="a" * 64,
            monitor_attempt_digest="b" * 64,
            source_request_id="okx-public-mark-price:1",
            requested_at="2026-08-06T10:59:59.900000Z",
            request_started_at="2026-08-06T10:59:59.950000Z",
            failure_at=RECEIVED_AT,
            monotonic_elapsed_ms=50,
            failure_code="PUBLIC_TIMEOUT",
        )
        self.assertEqual(
            receipt["transport_failure_digest"],
            verify_public_outcome_transport_failure(receipt),
        )
        self.assertTrue(receipt["no_response_received"])
        self.assertFalse(receipt["raw_capture_available"])
        self.assertFalse(receipt["retry_allowed"])
        self.assertNotIn("failure_summary", receipt)
        self.assertNotIn("exception", receipt)

        with self.assertRaisesRegex(
            V31OutcomeCaptureContractError, "FAILURE_CODE_INVALID"
        ):
            build_public_outcome_transport_failure(
                run_id="run:v31:capture-v2",
                cycle_index=1,
                monitor_plan_digest="a" * 64,
                monitor_attempt_digest="b" * 64,
                source_request_id="okx-public-mark-price:1",
                requested_at="2026-08-06T10:59:59.900000Z",
                request_started_at="2026-08-06T10:59:59.950000Z",
                failure_at=RECEIVED_AT,
                monotonic_elapsed_ms=50,
                failure_code="TimeoutError: secret provider detail",
            )


if __name__ == "__main__":
    unittest.main()
