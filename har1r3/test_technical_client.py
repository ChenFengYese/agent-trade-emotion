import copy
import hashlib
import importlib.util
import inspect
import json
import os
import pickle
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = ROOT / "har1r3" / "technical_client.py"
_SOCKET_TRIPWIRE = mock.patch.object(socket, "socket", side_effect=AssertionError("REAL_SOCKET_DENIED_IN_R3_OFFLINE_TEST"))
_SOCKET_TRIPWIRE.start()
SPEC = importlib.util.spec_from_file_location("har1r3_technical_client", CLIENT_PATH)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


def write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")


class TechnicalClientTest(unittest.TestCase):
    def setUp(self):
        self.wall_clock = mock.patch.object(CLIENT.time, "time", return_value=2_000_000_000)
        self.wall_clock.start()
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.directory = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        self.wall_clock.stop()

    def activation(self, serial=0, client_hash=None, test_hash=None):
        document = {
            "decision_id": "SOL_HAR1R3_TECH_REACHABILITY_ACTIVATION.v1",
            "permission": "ONE_THREE_PROBE_DIAGNOSTIC_BATCH",
            "issued_at_utc": "2033-05-18T03:30:%02dZ" % serial,
            "expires_at_utc": "2033-05-18T03:40:%02dZ" % serial,
            "bindings": {
                "r3_route_physical": CLIENT.R3_ROUTE_PHYSICAL_SHA256,
                "r3_route_canonical": CLIENT.R3_ROUTE_CANONICAL_SHA256,
                "r2_activation_physical": CLIENT.R2_ACTIVATION_PHYSICAL_SHA256,
                "r2_activation_canonical": CLIENT.R2_ACTIVATION_CANONICAL_SHA256,
                "r2_evidence_physical": CLIENT.R2_EVIDENCE_PHYSICAL_SHA256,
                "technical_plan_physical": CLIENT.TECHNICAL_PLAN_PHYSICAL_SHA256,
                "technical_plan_canonical": CLIENT.TECHNICAL_PLAN_CANONICAL_SHA256,
                "terms_contract_physical": CLIENT.TERMS_CONTRACT_PHYSICAL_SHA256,
                "terms_contract_canonical": CLIENT.TERMS_CONTRACT_CANONICAL_SHA256,
                "r2_client_physical": CLIENT.R2_CLIENT_PHYSICAL_SHA256,
                "client_physical": client_hash or hashlib.sha256(CLIENT_PATH.read_bytes()).hexdigest(),
                "test_physical": test_hash or hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "run_id": CLIENT.RUN_ID,
                "evidence_path": CLIENT.EVIDENCE_RELATIVE_PATH,
                "probes": CLIENT._probe_plan(),
            },
            "canonical_self_digest": {
                "algorithm": "SHA-256_CANONICAL_JSON",
                "digest_field": "activation_sha256",
                "domain_prefix_utf8": "msta-hed/har1r3-technical-activation/v1",
            },
        }
        return self.resign(document)

    def resign(self, document):
        unsigned = {key: value for key, value in document.items() if key != "activation_sha256"}
        document["activation_sha256"] = hashlib.sha256(
            b"msta-hed/har1r3-technical-activation/v1\0"
            + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return document

    def raw_activation(self, serial=0, document=None, **kwargs):
        document = self.activation(serial, **kwargs) if document is None else document
        return json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2).encode()

    def issue(self, serial=0, **kwargs):
        return CLIENT.issue_activation_capability(self.raw_activation(serial, **kwargs), now=2_000_000_000)

    class Response:
        def __init__(self, body=b"", status=200, headers=None):
            self.body, self.status, self.headers, self.closed = body, status, headers or {}, False

        def read(self, _count):
            return self.body

        def close(self):
            self.closed = True

    class Writer:
        def __init__(self):
            self.records = []

        def write(self, record):
            self.records.append(dict(record))

    def success_response(self, url):
        if url.endswith("README.md"):
            return self.Response(b"# binance-public-data\n")
        if url.endswith("CHECKSUM"):
            return self.Response(b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n")
        return self.Response(b"")

    def valid_evidence(self, serial):
        cap = self.issue(serial)
        path = self.directory / ("technical-%d.jsonl" % serial)
        writer = CLIENT._EvidenceWriter(path)
        writer.write(CLIENT._activation_record(cap, 2_000_000_000))
        CLIENT._run_with_transport(cap, lambda _method, url, _timeout: self.success_response(url), writer, lambda: 0)
        writer.close()
        return cap, path

    def test_static_contracts_strict_schema_canonical_hash_and_physical_hash(self):
        self.assertEqual(CLIENT.validate_technical_plan(ROOT / "har1r3/technical_plan.json"), CLIENT.TECHNICAL_PLAN_CANONICAL_SHA256)
        self.assertEqual(CLIENT.validate_terms_contract(ROOT / "har1r3/terms_evidence_contract.json"), CLIENT.TERMS_CONTRACT_CANONICAL_SHA256)
        self.assertEqual(hashlib.sha256((ROOT / "har1r3/technical_plan.json").read_bytes()).hexdigest(), CLIENT.TECHNICAL_PLAN_PHYSICAL_SHA256)
        self.assertEqual(hashlib.sha256((ROOT / "har1r3/terms_evidence_contract.json").read_bytes()).hexdigest(), CLIENT.TERMS_CONTRACT_PHYSICAL_SHA256)

    def test_contract_synchronized_bool_extra_and_navigation_drift_are_rejected(self):
        plan = json.loads((ROOT / "har1r3/technical_plan.json").read_text())
        plan["probes"][0]["sequence"] = True
        plan["extra"] = "denied"
        plan_path = self.directory / "plan.json"
        write_json(plan_path, plan)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.validate_technical_plan(plan_path)
        terms = json.loads((ROOT / "har1r3/terms_evidence_contract.json").read_text())
        terms["navigations"].reverse()
        unsigned = {key: value for key, value in terms.items() if key != "terms_evidence_contract_sha256"}
        terms["terms_evidence_contract_sha256"] = hashlib.sha256(
            b"msta-hed/har1r3-terms-evidence-contract/v1\0"
            + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        terms_path = self.directory / "terms.json"
        write_json(terms_path, terms)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.validate_terms_contract(terms_path)

    def test_closed_r2_artifacts_and_route_match_frozen_hashes(self):
        self.assertTrue(CLIENT.validate_closed_r2_artifacts())
        self.assertEqual(CLIENT._validate_route(ROOT / "config/sol_decision.har1r3-dual-lane-successor-route.v1.json"), CLIENT.R3_ROUTE_CANONICAL_SHA256)
        self.assertEqual(hashlib.sha256((ROOT / "har1r2/preflight_client.py").read_bytes()).hexdigest(), CLIENT.R2_CLIENT_PHYSICAL_SHA256)

    def test_exact_three_probe_and_terms_boundaries(self):
        self.assertEqual(CLIENT._probe_plan(), [
            {"sequence": 1, "method": "GET", "url": "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", "body_cap_bytes": 1048576},
            {"sequence": 2, "method": "HEAD", "url": "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip", "body_cap_bytes": 0},
            {"sequence": 3, "method": "GET", "url": "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip.CHECKSUM", "body_cap_bytes": 512},
        ])
        terms = CLIENT.load_strict_json(ROOT / "har1r3/terms_evidence_contract.json")
        self.assertEqual(len(terms["navigations"]), 2)
        self.assertTrue(all(value is False for value in terms["interaction_boundary"].values()))
        self.assertFalse(terms["legal_conclusion"])

    def test_wait_state_has_no_callback_network_or_evidence(self):
        called = []
        with self.assertRaises(PermissionError):
            CLIENT.require_future_sol_r3_activation(lambda: called.append(True))
        self.assertEqual(called, [])
        self.assertFalse((ROOT / "har1r3/technical_evidence.jsonl").exists())

    def test_raw_activation_rejects_dict_duplicate_nonfinite_bom_and_invalid_utf8(self):
        values = (self.activation(1), b'{"x":1,"x":2}', b'{"x":NaN}', b"\xef\xbb\xbf{}", b"\xff")
        for value in values:
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(CLIENT.ContractError):
                    CLIENT.issue_activation_capability(value, now=2_000_000_000)

    def test_activation_exact_types_nested_schema_and_self_hash(self):
        cases = (
            lambda d: d["bindings"]["probes"][0].__setitem__("sequence", True),
            lambda d: d["bindings"]["probes"][1].__setitem__("body_cap_bytes", 0.0),
            lambda d: d["bindings"]["probes"][0].__setitem__("extra", False),
            lambda d: d["bindings"]["probes"][0].pop("method"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                document = self.activation(2)
                mutate(document)
                self.resign(document)
                with self.assertRaisesRegex(CLIENT.ContractError, "activation binding: probes"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)
        document = self.activation(2)
        document["activation_sha256"] = "0" * 64
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_activation_ttl_zero_negative_and_over_900_rejected(self):
        cases = (
            ("2033-05-18T03:33:20Z", "2033-05-18T03:33:20Z"),
            ("2033-05-18T03:33:20Z", "2033-05-18T03:33:19Z"),
            ("2033-05-18T03:20:00Z", "2033-05-18T03:40:01Z"),
        )
        for issued, expires in cases:
            document = self.activation(3)
            document["issued_at_utc"], document["expires_at_utc"] = issued, expires
            self.resign(document)
            with self.subTest(issued=issued, expires=expires):
                with self.assertRaisesRegex(CLIENT.ContractError, "activation TTL"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_capability_opaque_single_process_single_use_and_concurrent(self):
        cap = self.issue(4)
        with self.assertRaises(PermissionError):
            copy.copy(cap)
        with self.assertRaises(PermissionError):
            copy.deepcopy(cap)
        with self.assertRaises(PermissionError):
            pickle.dumps(cap)
        outcomes = []
        def consume():
            try:
                CLIENT._consume_capability(cap, 2_000_000_000)
                outcomes.append(True)
            except PermissionError:
                outcomes.append(False)
        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 1)

    def test_activation_binds_route_r2_plan_terms_final_files_and_first_record(self):
        cap = self.issue(5)
        CLIENT._pre_tcp_recheck(cap)
        record = CLIENT._activation_record(cap, 2_000_000_000)
        self.assertEqual(record["bindings"]["r3_route_physical"], CLIENT.R3_ROUTE_PHYSICAL_SHA256)
        self.assertEqual(record["bindings"]["r2_evidence_physical"], CLIENT.R2_EVIDENCE_PHYSICAL_SHA256)
        self.assertEqual(record["bindings"]["r2_client_physical"], CLIENT.R2_CLIENT_PHYSICAL_SHA256)
        self.assertEqual(record["bindings"]["technical_plan_canonical"], CLIENT.TECHNICAL_PLAN_CANONICAL_SHA256)
        self.assertEqual(record["bindings"]["terms_contract_canonical"], CLIENT.TERMS_CONTRACT_CANONICAL_SHA256)
        self.assertEqual(record["probes"], CLIENT._probe_plan())

    def test_pre_tcp_rejects_nonexact_probe_and_final_file_hash_drift(self):
        cap = self.issue(6)
        cap._bindings["probes"][0]["sequence"] = True
        with self.assertRaisesRegex(CLIENT.ContractError, "frozen R3 probes drift"):
            CLIENT._pre_tcp_recheck(cap)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT._pre_tcp_recheck(self.issue(7, test_hash="0" * 64))

    def test_pre_tcp_rejects_same_content_final_symlink_and_nonregular_frozen_input(self):
        mirror = self.directory / "mirror"
        relatives = (
            "config/sol_decision.har1r3-dual-lane-successor-route.v1.json",
            "config/sol_activation.har1-btcusdt-source-preflight-r2f.v1.json",
            "har1r2/evidence.jsonl",
            "har1r3/technical_plan.json",
            "har1r3/terms_evidence_contract.json",
        )
        for relative in relatives:
            destination = mirror / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        route = mirror / relatives[0]
        same_content = route.with_name("same-content-route.json")
        same_content.write_bytes(route.read_bytes())
        route.unlink()
        os.symlink(same_content.name, route)
        with mock.patch.object(CLIENT, "ROOT", mirror):
            with self.assertRaisesRegex(CLIENT.ContractError, "regular non-symlink"):
                CLIENT._pre_tcp_recheck(self.issue(25))
        nonregular = self.directory / "nonregular"
        nonregular.mkdir()
        with self.assertRaisesRegex(CLIENT.ContractError, "regular non-symlink"):
            CLIENT._read_regular_nofollow(nonregular)

    def test_all_success_writes_three_probes_and_one_aggregate_terminal(self):
        writer, calls = self.Writer(), []
        def transport(method, url, timeout):
            calls.append((method, url, timeout))
            return self.success_response(url)
        self.assertTrue(CLIENT._run_with_transport(self.issue(8), transport, writer, lambda: 0))
        self.assertEqual(calls, [(method, url, 20) for _, method, url, _ in CLIENT.PROBES])
        self.assertEqual([record["record_type"] for record in writer.records], ["PROBE", "PROBE", "PROBE", "AGGREGATE_TERMINAL"])
        self.assertEqual([record["outcome"] for record in writer.records[:3]], ["SUCCESS"] * 3)
        self.assertTrue(writer.records[-1]["terminal"])
        self.assertEqual(writer.records[-1]["outcome"], "SUCCESS")

    def test_probe_one_failure_is_durable_and_does_not_short_circuit_two_or_three(self):
        writer, calls = self.Writer(), []
        def transport(_method, url, _timeout):
            calls.append(url)
            return self.Response(b"blocked", 500) if len(calls) == 1 else self.success_response(url)
        self.assertFalse(CLIENT._run_with_transport(self.issue(9), transport, writer, lambda: 0))
        self.assertEqual(calls, [probe[2] for probe in CLIENT.PROBES])
        self.assertEqual([record["outcome"] for record in writer.records[:3]], ["FAILURE", "SUCCESS", "SUCCESS"])
        self.assertEqual(writer.records[-1]["outcome"], "FAILURE")

    def test_timeout_failure_is_recorded_then_next_distinct_probes_continue(self):
        writer, calls = self.Writer(), []
        def transport(_method, url, _timeout):
            calls.append(url)
            if len(calls) == 1:
                raise TimeoutError("probe timeout")
            return self.success_response(url)
        self.assertFalse(CLIENT._run_with_transport(self.issue(11), transport, writer, lambda: 0))
        self.assertEqual(calls, [probe[2] for probe in CLIENT.PROBES])
        self.assertEqual(writer.records[0]["error"], "TimeoutError")
        self.assertEqual([record["outcome"] for record in writer.records[:3]], ["FAILURE", "SUCCESS", "SUCCESS"])

    def test_head_body_and_bad_checksum_fail_only_their_distinct_probe(self):
        for bad_sequence in (2, 3):
            writer, calls = self.Writer(), []
            def transport(_method, url, _timeout):
                sequence = len(calls) + 1
                calls.append(url)
                if sequence == bad_sequence:
                    return self.Response(b"x" if sequence == 2 else b"bad checksum")
                return self.success_response(url)
            with self.subTest(sequence=bad_sequence):
                self.assertFalse(CLIENT._run_with_transport(self.issue(10 + bad_sequence), transport, writer, lambda: 0))
                self.assertEqual(len(calls), 3)
                self.assertEqual(writer.records[bad_sequence - 1]["outcome"], "FAILURE")
                self.assertEqual(sum(record["outcome"] == "FAILURE" for record in writer.records[:3]), 1)

    def test_evidence_durability_failure_stops_all_later_network_and_no_aggregate(self):
        calls = []
        class BrokenWriter:
            def __init__(self):
                self.records = []
            def write(self, record):
                self.records.append(record)
                raise CLIENT.EvidenceDurabilityError("fsync")
        writer = BrokenWriter()
        with self.assertRaises(CLIENT.EvidenceDurabilityError):
            CLIENT._run_with_transport(self.issue(14), lambda _method, url, _timeout: calls.append(url) or self.success_response(url), writer, lambda: 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(writer.records), 1)
        self.assertEqual(writer.records[0]["record_type"], "PROBE")

    def test_total_budget_exhaustion_marks_remaining_probes_unattempted_without_network(self):
        class Clock:
            values = iter((0, 61, 61, 61))
            def __call__(self):
                return next(self.values)
        writer, calls = self.Writer(), []
        self.assertFalse(CLIENT._run_with_transport(self.issue(15), lambda _method, url, _timeout: calls.append(url) or self.success_response(url), writer, Clock()))
        self.assertEqual(len(calls), 1)
        self.assertTrue(writer.records[0]["request_attempted"])
        self.assertEqual([record["request_attempted"] for record in writer.records[1:3]], [False, False])
        self.assertTrue(all(record["error"] == "TOTAL_BUDGET_EXHAUSTED" for record in writer.records[1:3]))

    def test_deadline_factory_is_20_per_probe_and_excludes_evidence_time(self):
        limits = []
        class Deadline:
            def __init__(self, limit):
                limits.append(limit)
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
        class Clock:
            value = 0
            def __call__(self):
                return self.value
        clock = Clock()
        class SlowWriter(self.Writer):
            def write(inner, record):
                super(SlowWriter, inner).write(record)
                clock.value += 100
        writer = SlowWriter()
        self.assertTrue(CLIENT._run_with_transport(self.issue(16), lambda _method, url, _timeout: self.success_response(url), writer, clock, deadline_factory=Deadline))
        self.assertEqual(limits, [20, 20, 20])
        self.assertTrue(all(record["cumulative_elapsed_ms"] == 0 for record in writer.records[:3]))

    def test_postcheck_downgrades_successful_transport_return_at_20_second_deadline(self):
        class Clock:
            value = 0.0
            def __call__(self):
                return self.value
        clock, writer, calls = Clock(), self.Writer(), []
        def transport(_method, url, _timeout):
            calls.append(url)
            if len(calls) == 1:
                clock.value = 20.0
            return self.success_response(url)
        self.assertFalse(CLIENT._run_with_transport(self.issue(26), transport, writer, clock))
        self.assertEqual(len(calls), 3)
        self.assertEqual(writer.records[0]["outcome"], "FAILURE")
        self.assertEqual(writer.records[0]["error"], "PROBE_DEADLINE_EXCEEDED_AFTER_RETURN")
        self.assertEqual([record["outcome"] for record in writer.records[1:3]], ["SUCCESS", "SUCCESS"])
        self.assertEqual(writer.records[-1]["outcome"], "FAILURE")

    def test_just_below_20_second_boundary_remains_success_and_readback_valid(self):
        cap = self.issue(27)
        path, writer = self.directory / "near-boundary.jsonl", CLIENT._EvidenceWriter(self.directory / "near-boundary.jsonl")
        writer.write(CLIENT._activation_record(cap, 2_000_000_000))
        class Clock:
            value = 0.0
            def __call__(self):
                return self.value
        clock, calls = Clock(), []
        def transport(_method, url, _timeout):
            calls.append(url)
            if len(calls) == 1:
                clock.value = 19.999
            return self.success_response(url)
        self.assertTrue(CLIENT._run_with_transport(cap, transport, writer, clock))
        writer.close()
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        self.assertEqual(records[1]["request_elapsed_ms"], 19999)
        self.assertEqual(CLIENT._readback_sealed_evidence(path, cap, True)["protocol_outcome"], "SUCCESS")

    def test_response_is_closed_before_each_probe_record_write(self):
        responses = []
        class CloseCheckingWriter(self.Writer):
            def write(inner, record):
                if record["record_type"] == "PROBE":
                    self.assertTrue(responses[-1].closed)
                super(CloseCheckingWriter, inner).write(record)
        def transport(_method, url, _timeout):
            response = self.success_response(url)
            responses.append(response)
            return response
        writer = CloseCheckingWriter()
        self.assertTrue(CLIENT._run_with_transport(self.issue(17), transport, writer, lambda: 0))
        self.assertTrue(all(response.closed for response in responses))

    def test_writer_exclusive_nofollow_fsync_partial_write_and_raw_chain(self):
        path, writer = self.directory / "evidence.jsonl", CLIENT._EvidenceWriter(self.directory / "evidence.jsonl")
        real_write = CLIENT.os.write
        with mock.patch.object(CLIENT.os, "write", side_effect=lambda fd, data: real_write(fd, data[:1])):
            writer.write({"record_type": "X"})
            writer.write({"record_type": "Y"})
        writer.close()
        lines = path.read_bytes().splitlines()
        first, second = [json.loads(line) for line in lines]
        self.assertEqual(first["previous_sha256"], "0" * 64)
        self.assertEqual(second["previous_sha256"], hashlib.sha256(lines[0] + b"\n").hexdigest())
        with self.assertRaises(CLIENT.ContractError):
            CLIENT._EvidenceWriter(path).prepare()
        target = self.directory / "target"
        target.write_text("x")
        link = self.directory / "link"
        os.symlink(target, link)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT._EvidenceWriter(link).prepare()

    def test_close_success_strict_readback_returns_sealed_and_tamper_rejected(self):
        cap, path = self.valid_evidence(18)
        with mock.patch.object(CLIENT.os, "write", side_effect=AssertionError("readback wrote")), mock.patch.object(CLIENT.os, "fsync", side_effect=AssertionError("readback fsynced")):
            result = CLIENT._readback_sealed_evidence(path, cap, True)
        self.assertEqual(result, {"external_evidence_state": "SEALED", "protocol_outcome": "SUCCESS", "aggregate_terminal_reliable": True})
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        records[1]["sequence"] = True
        raw, previous = b"", "0" * 64
        for record in records:
            record["previous_sha256"] = previous
            line = CLIENT._canonical(record) + b"\n"
            raw += line
            previous = hashlib.sha256(line).hexdigest()
        tampered = self.directory / "tampered.jsonl"
        tampered.write_bytes(raw)
        with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
            CLIENT._readback_sealed_evidence(tampered, cap)

    def test_readback_rejects_rechained_activation_binding_and_aggregate_tamper(self):
        cap, path = self.valid_evidence(23)
        original = [json.loads(line) for line in path.read_bytes().splitlines()]
        cases = (
            ("activation-plan-bool", lambda records: records[0]["probes"][0].__setitem__("sequence", True)),
            ("activation-binding-float", lambda records: records[0]["bindings"]["probes"][1].__setitem__("body_cap_bytes", 0.0)),
            ("activation-extra", lambda records: records[0].__setitem__("extra", True)),
            ("activation-headers", lambda records: records[0]["request_headers"].__setitem__("Cookie", "forged")),
            ("aggregate-outcome", lambda records: records[4].__setitem__("outcome", "FAILURE")),
        )
        for name, mutate in cases:
            records = copy.deepcopy(original)
            mutate(records)
            raw, previous = b"", "0" * 64
            for record in records:
                record["previous_sha256"] = previous
                line = CLIENT._canonical(record) + b"\n"
                raw += line
                previous = hashlib.sha256(line).hexdigest()
            target = self.directory / (name + ".jsonl")
            target.write_bytes(raw)
            with self.subTest(name=name):
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
                    CLIENT._readback_sealed_evidence(target, cap)

    def test_readback_rejects_all_rechained_contradictory_success_variants(self):
        cap, path = self.valid_evidence(24)
        original = [json.loads(line) for line in path.read_bytes().splitlines()]
        def remove_status_and_body(records):
            for field in ("status_code", "response_bytes", "body_sha256", "body_base64"):
                records[1].pop(field)
        cases = (
            ("status-500", lambda records: records[1].__setitem__("status_code", 500)),
            ("missing-status", lambda records: records[1].pop("status_code")),
            ("missing-status-body", remove_status_and_body),
            ("missing-body-field", lambda records: records[1].pop("body_sha256")),
            ("body-sha", lambda records: records[1].__setitem__("body_sha256", "0" * 64)),
            ("response-bytes", lambda records: records[1].__setitem__("response_bytes", records[1]["response_bytes"] + 1)),
            ("empty-body-base64", lambda records: records[1].__setitem__("body_base64", "")),
            ("checksum-field", lambda records: records[3].__setitem__("checksum_sha256", "0" * 64)),
            ("success-with-error", lambda records: records[1].__setitem__("error", "ContractError")),
            ("probe-extra", lambda records: records[1].__setitem__("extra", True)),
            ("elapsed-bool", lambda records: records[1].__setitem__("request_elapsed_ms", True)),
            ("cumulative", lambda records: records[2].__setitem__("cumulative_elapsed_ms", 100)),
            ("timestamp-order", lambda records: records[1].__setitem__("response_completed_at_utc", "2033-05-18T03:29:00Z")),
            ("aggregate-success-count", lambda records: records[4].__setitem__("successful_probes", 2)),
            ("aggregate-failure-count", lambda records: records[4].__setitem__("failed_probes", 1)),
            ("aggregate-cumulative", lambda records: records[4].__setitem__("cumulative_elapsed_ms", 1)),
            ("aggregate-results", lambda records: records[4]["probe_results"][0].__setitem__("outcome", "FAILURE")),
            ("aggregate-extra", lambda records: records[4].__setitem__("extra", True)),
        )
        for name, mutate in cases:
            records = copy.deepcopy(original)
            mutate(records)
            raw, previous = b"", "0" * 64
            for record in records:
                record["previous_sha256"] = previous
                line = CLIENT._canonical(record) + b"\n"
                raw += line
                previous = hashlib.sha256(line).hexdigest()
            target = self.directory / ("contradictory-" + name + ".jsonl")
            target.write_bytes(raw)
            with self.subTest(name=name):
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
                    CLIENT._readback_sealed_evidence(target, cap)

    def test_readback_replays_total_budget_and_rejects_rechained_attempt_state_forgery(self):
        cap, path = self.valid_evidence(28)
        original = [json.loads(line) for line in path.read_bytes().splitlines()]
        def make_unattempted(record, cumulative=0):
            for field in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers", "checksum_sha256", "checksum_basename"):
                record.pop(field, None)
            record["request_attempted"] = False
            record["outcome"] = "FAILURE"
            record["error"] = "TOTAL_BUDGET_EXHAUSTED"
            record["request_elapsed_ms"] = 0
            record["cumulative_elapsed_ms"] = cumulative
        def derive_aggregate(records):
            probes, aggregate = records[1:4], records[4]
            aggregate["outcome"] = "SUCCESS" if all(record["outcome"] == "SUCCESS" for record in probes) else "FAILURE"
            aggregate["probe_results"] = [{"sequence": record["sequence"], "outcome": record["outcome"], "request_attempted": record["request_attempted"]} for record in probes]
            aggregate["successful_probes"] = sum(record["outcome"] == "SUCCESS" for record in probes)
            aggregate["failed_probes"] = sum(record["outcome"] == "FAILURE" for record in probes)
            aggregate["cumulative_elapsed_ms"] = probes[-1]["cumulative_elapsed_ms"]
        def huge_terminal_failure(records):
            record = records[3]
            for field in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers", "checksum_sha256", "checksum_basename"):
                record.pop(field, None)
            record["request_attempted"] = True
            record["outcome"] = "FAILURE"
            record["error"] = "TimeoutError"
            record["request_elapsed_ms"] = 400000
            record["cumulative_elapsed_ms"] = 400000
            derive_aggregate(records)
        def skipped_then_resumed(records):
            make_unattempted(records[1], 0)
            derive_aggregate(records)
        def all_skipped_at_zero(records):
            for record in records[1:4]:
                make_unattempted(record, 0)
            derive_aggregate(records)
        def valid_skip_then_illegal_resume(records):
            records[1]["outcome"] = "FAILURE"
            records[1]["error"] = "PROBE_DEADLINE_EXCEEDED_AFTER_RETURN"
            records[1]["request_elapsed_ms"] = 60000
            records[1]["cumulative_elapsed_ms"] = 60000
            make_unattempted(records[2], 60000)
            records[3]["request_elapsed_ms"] = 0
            records[3]["cumulative_elapsed_ms"] = 60000
            derive_aggregate(records)
        cases = (
            ("huge-terminal-failure-elapsed", huge_terminal_failure),
            ("skipped-then-resumed", skipped_then_resumed),
            ("all-skipped-at-zero", all_skipped_at_zero),
            ("valid-skip-then-illegal-resume", valid_skip_then_illegal_resume),
        )
        for name, mutate in cases:
            records = copy.deepcopy(original)
            mutate(records)
            raw, previous = b"", "0" * 64
            for record in records:
                record["previous_sha256"] = previous
                line = CLIENT._canonical(record) + b"\n"
                raw += line
                previous = hashlib.sha256(line).hexdigest()
            target = self.directory / ("budget-" + name + ".jsonl")
            target.write_bytes(raw)
            with self.subTest(name=name):
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
                    CLIENT._readback_sealed_evidence(target, cap)

    def test_readback_allows_failure_to_exhaust_remaining_budget_and_rejects_recovery(self):
        cap, path = self.valid_evidence(29)
        original = [json.loads(line) for line in path.read_bytes().splitlines()]

        def derive_aggregate(records):
            probes, aggregate = records[1:4], records[4]
            aggregate["outcome"] = "SUCCESS" if all(record["outcome"] == "SUCCESS" for record in probes) else "FAILURE"
            aggregate["probe_results"] = [{"sequence": record["sequence"], "outcome": record["outcome"], "request_attempted": record["request_attempted"]} for record in probes]
            aggregate["successful_probes"] = sum(record["outcome"] == "SUCCESS" for record in probes)
            aggregate["failed_probes"] = sum(record["outcome"] == "FAILURE" for record in probes)
            aggregate["cumulative_elapsed_ms"] = probes[-1]["cumulative_elapsed_ms"]

        # Two prior valid successes each consume 19,999ms; the allowed one-ms
        # cumulative rounding delta places the ledger at 40,000ms.  That
        # leaves exactly one legal 20-second budget slice for the first
        # failure.  It is the terminal probe, so this is the only
        # sequence-reachable exhausted-budget evidence shape.
        records = copy.deepcopy(original)
        for index, cumulative in ((1, 20000), (2, 40000)):
            records[index]["request_elapsed_ms"] = 19999
            records[index]["cumulative_elapsed_ms"] = cumulative
        failure = records[3]
        for field in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers", "checksum_sha256", "checksum_basename"):
            failure.pop(field, None)
        failure["request_attempted"] = True
        failure["outcome"] = "FAILURE"
        failure["error"] = "TimeoutError"
        failure["request_elapsed_ms"] = 20000
        failure["cumulative_elapsed_ms"] = 60000
        derive_aggregate(records)

        def rechained(items, target):
            raw, previous = b"", "0" * 64
            for item in items:
                item["previous_sha256"] = previous
                line = CLIENT._canonical(item) + b"\n"
                raw += line
                previous = hashlib.sha256(line).hexdigest()
            target.write_bytes(raw)

        valid = self.directory / "budget-exhausted-terminal-failure.jsonl"
        rechained(records, valid)
        self.assertEqual(CLIENT._readback_sealed_evidence(valid, cap)["protocol_outcome"], "FAILURE")

        # A fourth actual probe cannot exist in the fixed three-probe record
        # shape.  Model the forbidden recovery by making the final slot an
        # attempted request after a first-slot exhausted budget; it must fail
        # both the per-probe deadline and total-budget replay checks.
        recovery = copy.deepcopy(original)
        first = recovery[1]
        for field in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers", "checksum_sha256", "checksum_basename"):
            first.pop(field, None)
        first["request_attempted"] = True
        first["outcome"] = "FAILURE"
        first["error"] = "TimeoutError"
        first["request_elapsed_ms"] = 60000
        first["cumulative_elapsed_ms"] = 60000
        for record in recovery[2:4]:
            for field in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers", "checksum_sha256", "checksum_basename"):
                record.pop(field, None)
            record["request_attempted"] = True
            record["outcome"] = "FAILURE"
            record["error"] = "TimeoutError"
            record["request_elapsed_ms"] = 0
            record["cumulative_elapsed_ms"] = 60000
        derive_aggregate(recovery)
        invalid = self.directory / "budget-exhausted-recovery.jsonl"
        rechained(recovery, invalid)
        with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
            CLIENT._readback_sealed_evidence(invalid, cap)

    def test_readback_rejects_chain_duplicate_final_symlink_and_nonregular(self):
        cap, path = self.valid_evidence(19)
        raw = path.read_bytes()
        duplicate = self.directory / "duplicate.jsonl"
        duplicate.write_bytes(raw.replace(b'"record_type":"ACTIVATION"', b'"record_type":"ACTIVATION","record_type":"ACTIVATION"', 1))
        broken_chain = self.directory / "chain.jsonl"
        lines = raw.splitlines()
        broken_chain.write_bytes(lines[0] + b"\n" + lines[1].replace(json.loads(lines[1])["previous_sha256"].encode(), b"0" * 64, 1) + b"\n" + b"\n".join(lines[2:]) + b"\n")
        directory = self.directory / "directory"
        directory.mkdir()
        link = self.directory / "link.jsonl"
        os.symlink(path, link)
        for target in (duplicate, broken_chain, directory, link):
            with self.subTest(target=target.name):
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError):
                    CLIENT._readback_sealed_evidence(target, cap)

    def test_activation_write_failure_zero_transport_and_capability_consumed(self):
        calls = []
        class BrokenWriter:
            def __init__(self, _path):
                pass
            def prepare(self):
                pass
            def write(self, _record):
                raise CLIENT.EvidenceDurabilityError("write")
            def close(self):
                pass
        class Opener:
            def open(self, *_args, **_kwargs):
                calls.append(True)
                raise AssertionError("transport")
        cap = self.issue(20)
        with mock.patch.object(CLIENT, "_EvidenceWriter", BrokenWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                CLIENT.run_technical_preflight(cap)
        self.assertEqual(calls, [])
        with self.assertRaises(PermissionError):
            CLIENT.run_technical_preflight(cap)

    def test_close_failure_after_fsynced_aggregate_is_distinct_and_not_sealed(self):
        calls, records = [], []
        class CloseBrokenWriter:
            def __init__(self, _path):
                pass
            def prepare(self):
                pass
            def write(self, record):
                records.append(dict(record))
            def close(self):
                raise OSError("close")
        class Opener:
            def open(inner, request, **_kwargs):
                calls.append(request.full_url)
                return self.success_response(request.full_url)
        cap = self.issue(21)
        with mock.patch.object(CLIENT, "_EvidenceWriter", CloseBrokenWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            with self.assertRaises(CLIENT.EvidenceCloseFailureAfterFsyncError) as raised:
                CLIENT.run_technical_preflight(cap)
        self.assertEqual(raised.exception.external_evidence_state, "REVIEW_REQUIRED_CLOSE_ERROR")
        self.assertEqual(len(calls), 3)
        self.assertEqual(records[-1]["record_type"], "AGGREGATE_TERMINAL")
        self.assertNotIn("sealed", records[-1])

    def test_production_entry_with_temp_writer_closes_readbacks_and_returns_sealed(self):
        path = self.directory / "production.jsonl"
        class TempWriter(CLIENT._EvidenceWriter):
            def __init__(self, _path):
                super().__init__(path)
        class Opener:
            def open(inner, request, **_kwargs):
                return self.success_response(request.full_url)
        cap = self.issue(22)
        with mock.patch.object(CLIENT, "_EvidenceWriter", TempWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            result = CLIENT.run_technical_preflight(cap)
        self.assertEqual(result["external_evidence_state"], "SEALED")
        self.assertEqual(result["protocol_outcome"], "SUCCESS")
        self.assertEqual(len(path.read_bytes().splitlines()), 5)

    def test_proxy_no_bypass_redirect_cookie_auth_and_no_zip_get(self):
        opener = CLIENT._build_production_opener()
        self.assertTrue(any(isinstance(handler, CLIENT._ForcedHttpsProxyHandler) for handler in opener.handlers))
        self.assertFalse(any(isinstance(handler, CLIENT.urllib.request.HTTPCookieProcessor) for handler in opener.handlers))
        self.assertFalse(any("AuthHandler" in type(handler).__name__ for handler in opener.handlers))
        request = CLIENT._production_request("HEAD", CLIENT.PROBES[1][2])
        with mock.patch.object(CLIENT.urllib.request, "proxy_bypass", side_effect=AssertionError("proxy bypass")):
            CLIENT._ForcedHttpsProxyHandler().proxy_open(request, CLIENT.PROXY, "https")
        self.assertEqual(request.host, "127.0.0.1:7897")
        self.assertEqual(request._tunnel_host, "data.binance.vision")
        self.assertEqual(CLIENT.PROBES[1][1], "HEAD")
        self.assertFalse(any(method == "GET" and url.endswith(".zip") for _, method, url, _ in CLIENT.PROBES))

    def test_socket_tripwire_precedes_r3_and_r2_import_and_remains_active(self):
        self.assertIsNotNone(_SOCKET_TRIPWIRE)
        self.assertEqual(CLIENT.R2_SAFETY._physical(ROOT / "har1r2/preflight_client.py"), CLIENT.R2_CLIENT_PHYSICAL_SHA256)
        with self.assertRaises(AssertionError):
            socket.socket()

    def test_production_entry_has_no_transport_injection_and_outputs_remain_absent(self):
        self.assertEqual(list(inspect.signature(CLIENT.run_technical_preflight).parameters), ["capability"])
        self.assertFalse((ROOT / "har1r3/technical_evidence.jsonl").exists())
        self.assertFalse((ROOT / "har1r3/terms_evidence").exists())


if __name__ == "__main__":
    unittest.main()
