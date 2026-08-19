import ast
import base64
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
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = ROOT / "har1r2" / "preflight_client.py"
# This process-wide tripwire starts before the subject module is imported and
# remains live through every offline test. Mock transports below never touch it.
_SOCKET_TRIPWIRE = mock.patch.object(socket, "socket", side_effect=AssertionError("REAL_SOCKET_DENIED_IN_OFFLINE_TEST"))
_SOCKET_TRIPWIRE.start()
SPEC = importlib.util.spec_from_file_location("har1r2_client", CLIENT_PATH)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


def write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")


def baseline_self_hash(document):
    copy = dict(document)
    copy.pop("baseline_sha256")
    encoded = json.dumps(copy, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"msta-hed/har1r2-baseline/v1\0" + encoded).hexdigest()


class Har1R2StaticTest(unittest.TestCase):
    def setUp(self):
        self.wall_clock_patcher = mock.patch.object(CLIENT.time, "time", return_value=2_000_000_000)
        self.wall_clock_patcher.start()
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        self.wall_clock_patcher.stop()

    def copy_json(self, relative):
        path = self.dir / Path(relative).name
        path.write_bytes((ROOT / relative).read_bytes())
        return path

    def baseline_document(self):
        return json.loads((ROOT / "har1r2/baseline.json").read_text(encoding="utf-8"))

    def baseline_fixture(self, mutate):
        document = self.baseline_document()
        mutate(document)
        path = self.dir / "baseline.json"
        write_json(path, document)
        return path

    def test_v1_sealed_hashes_are_unchanged(self):
        expected = {"har1/baseline.json": "61b36e229466a88fb85259f089c1b4fe606ec4c9c7ee3f8a29d8179e9c10eb12", "har1/source_contract.json": "16087fa87ea1c55027bc8e64bd793ac76b17b75616f4c932bb41f8bba9b174bf", "har1/purge_plan.json": "8dbd22281844300e9c6432f32ce3a94a0ef94f58bb583b2c6222d8648be6d2d8"}
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_baseline_complete_roundtrip_and_self_hash(self):
        self.assertEqual(CLIENT.validate_baseline(ROOT / "har1r2/baseline.json"), "5873a0d363c2746799fbc8019cddd0af020e998013cea48e608838e4a05bbf2b")

    def test_baseline_bad_base64_hash_count_and_self_hash_rejected(self):
        cases = [
            lambda d: d.__setitem__("raw_status_base64", "not base64!"),
            lambda d: d.__setitem__("raw_status_sha256", "0" * 64),
            lambda d: d.__setitem__("raw_status_byte_count", d["raw_status_byte_count"] + 1),
            lambda d: d.__setitem__("baseline_sha256", "0" * 64),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                with self.assertRaises(CLIENT.ContractError):
                    CLIENT.validate_baseline(self.baseline_fixture(mutate))

    def test_baseline_projection_order_branch_head_route_and_time_rejected(self):
        cases = [
            lambda d: d.__setitem__("path_projection", list(reversed(d["path_projection"]))),
            lambda d: d.__setitem__("branch", "wrong"),
            lambda d: d.__setitem__("route_id", "wrong"),
            lambda d: d.__setitem__("capture_started_at_utc", "2026-07-29T08:52:57Z"),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                with self.assertRaises(CLIENT.ContractError):
                    CLIENT.validate_baseline(self.baseline_fixture(mutate))

    def test_synchronized_raw_header_document_and_selfhash_tamper_rejected(self):
        document = self.baseline_document()
        raw = base64.b64decode(document["raw_status_base64"])
        raw = raw.replace(b"# branch.oid 7ca3fc4f99a57f98217e703f222b295653ace87e", b"# branch.oid deadbeef")
        raw = raw.replace(b"# branch.head codex/s0-research-foundation", b"# branch.head attacker-branch")
        records = raw[:-1].split(b"\0")
        document["raw_status_base64"] = base64.b64encode(raw).decode("ascii")
        document["raw_status_sha256"] = hashlib.sha256(raw).hexdigest()
        document["raw_status_byte_count"] = len(raw)
        document["nul_delimiter_count"] = len(records)
        document["raw_record_count"] = len(records)
        document["raw_records_base64_in_order"] = [base64.b64encode(item).decode("ascii") for item in records]
        document["branch"] = "attacker-branch"
        document["head"] = "deadbeef"
        document["baseline_sha256"] = baseline_self_hash(document)
        path = self.dir / "synchronized-tamper.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_baseline(path)

    def test_porcelain_truncation_nonutf8_newline_and_all_path_kinds(self):
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.parse_porcelain_v2_z(b"? truncated")
        raw = (b"# branch.oid abc\0# branch.head branch\0"
               b"1 .M N... 1 1 1 aa bb ordinary name\n\0"
               b"2 .M N... 1 1 1 aa bb R100 renamed\n\0old \xff\n\0"
               b"u UU N... 1 2 3 4 aa bb cc unmerged\n\0"
               b"? untracked \xff\n\0! ignored name\n\0")
        records, projection, branch, head = CLIENT.parse_porcelain_v2_z(raw)
        self.assertEqual(len(records), 8)
        self.assertEqual((branch, head), ("branch", "abc"))
        self.assertEqual([item["record_kind"] for item in projection], ["1", "2", "2", "u", "?", "!"])
        self.assertIn(base64.b64encode(b"old \xff\n").decode("ascii"), [item["path_bytes_base64"] for item in projection])
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.parse_porcelain_v2_z(b"# branch.oid a\0# branch.oid b\0# branch.head c\0? path\0")

    def test_duplicate_json_and_nonfinite_are_rejected(self):
        duplicate = self.dir / "duplicate.json"; duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
        nonfinite = self.dir / "nonfinite.json"; nonfinite.write_text('{"a": NaN}', encoding="utf-8")
        for path in (duplicate, nonfinite):
            with self.assertRaises(CLIENT.ContractError): CLIENT.load_strict_json(path)

    def test_source_exact_manifest_requests_scope_and_terms(self):
        self.assertEqual(CLIENT.validate_source_contract(ROOT / "har1r2/source_contract.json"), "42cd256a574f7ddeb1c8930c9ba4d43c4e177dadb1470eada832801cfb7dfafe")
        document = json.loads((ROOT / "har1r2/source_contract.json").read_text())
        document["object_manifest"]["objects"].reverse()
        path = self.dir / "source.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_source_contract(path)
        document = json.loads((ROOT / "har1r2/source_contract.json").read_text())
        document["extra"] = True
        path = self.dir / "source-extra.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_source_contract(path)
        document = json.loads((ROOT / "har1r2/source_contract.json").read_text())
        document.pop("source_contract_sha256")
        path = self.dir / "source-missing-digest.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_source_contract(path)
        document = json.loads((ROOT / "har1r2/source_contract.json").read_text())
        document["future_five_request_plan"]["requests"][3]["method"] = "GET"
        path = self.dir / "source-requests.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_source_contract(path)

    def test_purge_exact_roles_windows_policy_and_unvalidated_status(self):
        self.assertEqual(CLIENT.validate_purge_plan(ROOT / "har1r2/purge_plan.json"), "a9d4d3ed55a1354613a3c641be6478372a692ddcb87077187e5e5f56e0e74c3f")
        document = json.loads((ROOT / "har1r2/purge_plan.json").read_text())
        document["eligible_decision_windows_after_purge"][0]["end_exclusive"] = "2025-12-26T00:00:00Z"
        path = self.dir / "purge.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_purge_plan(path)
        document = json.loads((ROOT / "har1r2/purge_plan.json").read_text())
        document["extra"] = True
        path = self.dir / "purge-extra.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_purge_plan(path)
        document = json.loads((ROOT / "har1r2/purge_plan.json").read_text())
        document.pop("purge_plan_sha256")
        path = self.dir / "purge-missing-digest.json"; write_json(path, document)
        with self.assertRaises(CLIENT.ContractError): CLIENT.validate_purge_plan(path)

    def test_existing_symlink_and_nonregular_targets_rejected(self):
        self.assertIsNone(CLIENT.reject_existing_target(self.dir / "absent"))
        regular = self.dir / "regular"; regular.write_text("x")
        with self.assertRaises(CLIENT.ContractError): CLIENT.reject_existing_target(regular)
        directory = self.dir / "directory"; directory.mkdir()
        with self.assertRaises(CLIENT.ContractError): CLIENT.reject_existing_target(directory)
        link = self.dir / "link"; os.symlink(regular, link)
        with self.assertRaises(CLIENT.ContractError): CLIENT.reject_existing_target(link)
        parent = self.dir / "parent"; parent.mkdir()
        parent_link = self.dir / "parent-link"; os.symlink(parent, parent_link)
        with self.assertRaises(CLIENT.ContractError): CLIENT.reject_existing_target(parent_link / "child")

    def activation(self, serial=0, client_hash=None, test_hash=None):
        document = {
            "decision_id": "SOL_HAR1R2_SOURCE_PREFLIGHT_ACTIVATION.v1",
            "permission": "ONE_BOUNDED_FIVE_REQUEST_PREFLIGHT",
            "issued_at_utc": "2033-05-18T03:30:%02dZ" % serial,
            "expires_at_utc": "2033-05-18T03:40:%02dZ" % serial,
            "bindings": {
                "r2_route_physical": CLIENT.ROUTE_PHYSICAL_SHA256, "r2_route_canonical": CLIENT.ROUTE_CANONICAL_SHA256,
                "r2d_route_physical": CLIENT.R2D_ROUTE_PHYSICAL_SHA256, "r2d_route_canonical": CLIENT.R2D_ROUTE_CANONICAL_SHA256,
                "r2e_route_physical": CLIENT.R2E_ROUTE_PHYSICAL_SHA256, "r2e_route_canonical": CLIENT.R2E_ROUTE_CANONICAL_SHA256,
                "r2f_route_physical": CLIENT.R2F_ROUTE_PHYSICAL_SHA256, "r2f_route_canonical": CLIENT.R2F_ROUTE_CANONICAL_SHA256,
                "baseline_physical": CLIENT._BASELINE_PHYSICAL, "baseline_canonical": CLIENT._BASELINE_CANONICAL,
                "source_physical": CLIENT._SOURCE_PHYSICAL, "source_canonical": CLIENT._SOURCE_CANONICAL,
                "purge_physical": CLIENT._PURGE_PHYSICAL, "purge_canonical": CLIENT._PURGE_CANONICAL,
                "client_physical": client_hash or hashlib.sha256(CLIENT_PATH.read_bytes()).hexdigest(),
                "test_physical": test_hash or hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "run_id": CLIENT.RUN_ID, "evidence_path": "har1r2/evidence.jsonl", "request_plan": CLIENT._request_plan(),
            },
            "canonical_self_digest": {"domain_prefix_utf8": "msta-hed/har1r2-activation/v1", "digest_field": "activation_sha256", "algorithm": "SHA-256_CANONICAL_JSON"},
        }
        document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return document

    def resign_activation(self, document):
        unsigned = {key: value for key, value in document.items() if key != "activation_sha256"}
        document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return document

    def raw_activation(self, serial=0, client_hash=None, test_hash=None, document=None):
        document = self.activation(serial, client_hash, test_hash) if document is None else document
        return json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2).encode("utf-8")

    def issue(self, serial=0, **kwargs):
        return CLIENT.issue_activation_capability(self.raw_activation(serial, **kwargs), now=2_000_000_000)

    class Response:
        def __init__(self, body=b"", status=200, headers=None):
            self.body, self.status, self.headers, self.closed = body, status, headers or {}, False
        def read(self, _count): return self.body
        def close(self): self.closed = True

    class Writer:
        def __init__(self): self.records = []
        def write(self, record): self.records.append(dict(record))

    def sealed_failure_file(self, serial):
        cap = self.issue(serial)
        path = self.dir / ("sealed-%d.jsonl" % serial)
        writer = CLIENT._EvidenceWriter(path)
        writer.write(CLIENT._activation_record(cap, 2_000_000_000))
        sequence, method, url, _cap = CLIENT.FUTURE_REQUESTS[0]
        writer.write({"schema_version": CLIENT.EVIDENCE_SCHEMA_VERSION, "record_type": "TERMINAL", "terminal": True,
                      "outcome": "FAILURE", "sequence": sequence, "method": method, "url": url})
        writer.close()
        return cap, path

    def test_wait_state_rejects_before_callback_write_or_network(self):
        called = []
        with self.assertRaises(PermissionError): CLIENT.require_future_sol_r2_activation(lambda: called.append(True))
        self.assertEqual(called, [])
        source = CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("def run_preflight", source)
        self.assertFalse((ROOT / "har1r2/evidence.jsonl").exists())

    def test_activation_selfhash_permission_bindings_and_time_are_strict(self):
        document = self.activation(1); document["activation_sha256"] = "0" * 64
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)
        document = self.activation(2); document["permission"] = "ESCALATE"; document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps({k:v for k,v in document.items() if k != "activation_sha256"}, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)
        document = self.activation(3); document["bindings"]["run_id"] = "wrong"; document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps({k:v for k,v in document.items() if k != "activation_sha256"}, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)
        future = self.activation(4)
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=future), now=1)

    def test_raw_activation_rejects_dict_duplicate_nonfinite_invalid_utf8_and_bom(self):
        extra = self.activation(10); extra["extra"] = True
        missing = self.activation(11); missing.pop("permission")
        invalid = (
            self.activation(9),
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b'\xff',
            b'\xef\xbb\xbf{}',
            self.raw_activation(document=extra),
            self.raw_activation(document=missing),
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(value, now=2_000_000_000)

    def test_self_hashed_activation_rejects_boolean_sequence_and_body_cap(self):
        cases = (
            lambda document: document["bindings"]["request_plan"][0].__setitem__("sequence", True),
            lambda document: document["bindings"]["request_plan"][3].__setitem__("body_cap_bytes", False),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                document = self.activation(10)
                mutate(document)
                self.resign_activation(document)
                with self.assertRaisesRegex(CLIENT.ContractError, "activation binding: request_plan"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_self_hashed_activation_rejects_integral_float_sequence_and_body_cap(self):
        cases = (
            lambda document: document["bindings"]["request_plan"][0].__setitem__("sequence", 1.0),
            lambda document: document["bindings"]["request_plan"][3].__setitem__("body_cap_bytes", 0.0),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                document = self.activation(11)
                mutate(document)
                self.resign_activation(document)
                with self.assertRaisesRegex(CLIENT.ContractError, "activation binding: request_plan"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_self_hashed_activation_rejects_nested_request_extra_or_missing_fields(self):
        cases = (
            lambda document: document["bindings"]["request_plan"][0].__setitem__("extra", True),
            lambda document: document["bindings"]["request_plan"][0].pop("method"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                document = self.activation(12)
                mutate(document)
                self.resign_activation(document)
                with self.assertRaisesRegex(CLIENT.ContractError, "activation binding: request_plan"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_activation_ttl_zero_negative_and_over_900_seconds_are_rejected(self):
        cases = (
            ("2033-05-18T03:33:20Z", "2033-05-18T03:33:20Z"),
            ("2033-05-18T03:33:20Z", "2033-05-18T03:33:19Z"),
            ("2033-05-18T03:20:00Z", "2033-05-18T03:40:01Z"),
        )
        for issued, expires in cases:
            with self.subTest(issued=issued, expires=expires):
                document = self.activation(13)
                document["issued_at_utc"], document["expires_at_utc"] = issued, expires
                self.resign_activation(document)
                with self.assertRaisesRegex(CLIENT.ContractError, "activation TTL"):
                    CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_activation_binds_exact_run_evidence_and_request_plan(self):
        document = self.activation(7)
        document["bindings"]["request_plan"][0]["url"] = "https://wrong.invalid"
        unsigned = {key: value for key, value in document.items() if key != "activation_sha256"}
        document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_r2f_route_is_bound_in_capability_first_evidence_and_pre_tcp_recheck(self):
        cap = self.issue(56)
        self.assertEqual(cap._bindings["r2f_route_physical"], "cbe15f0883825148e2a93187b8faa7f96a7d9ff996fe1636f77d0fc3f928a517")
        self.assertEqual(cap._bindings["r2f_route_canonical"], "793c77dc38a4f310c78decdbde52461a2732ee6fad25e404a99a97209bb6103f")
        record = CLIENT._activation_record(cap, 2_000_000_000)
        self.assertEqual(record["bindings"]["r2f_route_physical"], CLIENT.R2F_ROUTE_PHYSICAL_SHA256)
        CLIENT._pre_tcp_recheck(cap)
        document = self.activation(57)
        document["bindings"]["r2f_route_canonical"] = "0" * 64
        self.resign_activation(document)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_pre_tcp_recheck_rejects_nonexact_frozen_request_plan(self):
        cap = self.issue(57)
        cap._bindings["request_plan"][0]["sequence"] = True
        with self.assertRaisesRegex(CLIENT.ContractError, "frozen request plan drift"):
            CLIENT._pre_tcp_recheck(cap)

    def test_r2e_route_is_bound_in_activation_capability_and_pre_tcp_recheck(self):
        cap = self.issue(48)
        self.assertEqual(cap._bindings["r2e_route_physical"], "fbbb48fc700bc5258c9bfd049676896b2475990fff64bf879eedad811e61dc71")
        self.assertEqual(cap._bindings["r2e_route_canonical"], "666354ec75eaee6fcf02c7ccf7a31e542d091514812b0ffe9d4f7f66bb095884")
        self.assertEqual(CLIENT._activation_record(cap, 2_000_000_000)["bindings"]["r2e_route_canonical"], CLIENT.R2E_ROUTE_CANONICAL_SHA256)
        CLIENT._pre_tcp_recheck(cap)
        document = self.activation(49)
        document["bindings"]["r2e_route_physical"] = "0" * 64
        unsigned = {key: value for key, value in document.items() if key != "activation_sha256"}
        document["activation_sha256"] = hashlib.sha256(b"msta-hed/har1r2-activation/v1\0" + json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(CLIENT.ContractError): CLIENT.issue_activation_capability(self.raw_activation(document=document), now=2_000_000_000)

    def test_global_socket_tripwire_was_active_before_client_import_and_remains_active(self):
        self.assertIsNotNone(_SOCKET_TRIPWIRE)
        with self.assertRaises(AssertionError):
            socket.socket()

    def test_capability_deep_copies_activation_bindings_after_issue(self):
        document = self.activation(8)
        expected_plan = json.loads(json.dumps(document["bindings"]["request_plan"]))
        raw = self.raw_activation(document=document)
        cap = CLIENT.issue_activation_capability(raw, now=2_000_000_000)
        document["bindings"]["request_plan"][0]["url"] = "https://mutated.invalid"
        CLIENT._pre_tcp_recheck(cap)
        header = CLIENT._activation_record(cap, 2_000_000_000)
        self.assertEqual(header["request_plan"], expected_plan)
        self.assertEqual(header["activation_raw_physical_sha256"], hashlib.sha256(raw).hexdigest())

    def test_capability_is_opaque_single_process_one_time_and_concurrent(self):
        cap = self.issue(5)
        with self.assertRaises(PermissionError): copy.copy(cap)
        with self.assertRaises(PermissionError): copy.deepcopy(cap)
        with self.assertRaises(PermissionError): pickle.dumps(cap)
        outcomes = []
        threads = [threading.Thread(target=lambda: outcomes.append(self._consume(cap))) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 1)
        with self.assertRaises(PermissionError): CLIENT._consume_capability(cap, 2_000_000_000)
        with self.assertRaises(PermissionError): CLIENT.issue_activation_capability(self.raw_activation(5), now=2_000_000_000)

    def _consume(self, cap):
        try:
            CLIENT._consume_capability(cap, 2_000_000_000)
            return True
        except PermissionError:
            return False

    def test_fixed_five_request_order_caps_headers_close_and_checksum_evidence(self):
        cap = self.issue(6)
        calls, writer = [], self.Writer()
        def fake(method, url, timeout):
            calls.append((method, url, timeout))
            body = b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if method == "GET" and url.endswith("CHECKSUM") else b""
            return self.Response(body, headers={"Strict-Transport-Security": "max-age=1", "Set-Cookie": "ignored"})
        self.assertTrue(CLIENT._run_with_transport(cap, fake, writer, lambda: 0))
        self.assertEqual(calls, [(m, u, 20) for _, m, u, _ in CLIENT.FUTURE_REQUESTS])
        self.assertEqual(len(writer.records), 5)
        self.assertEqual([record["sequence"] for record in writer.records], [1, 2, 3, 4, 5])
        self.assertEqual(writer.records[-1]["checksum_basename"], "BTCUSDT-1m-2025-07.zip")
        self.assertEqual(writer.records[-1]["checksum_sha256"], "a" * 64)
        self.assertTrue(writer.records[-1]["terminal"])
        self.assertNotIn("Set-Cookie", writer.records[0]["security_headers"])
        self.assertTrue(all("request_started_at_utc" in record and "response_completed_at_utc" in record for record in writer.records))

    def test_error_paths_have_one_terminal_and_close_response(self):
        cases = [("status", lambda _seq: self.Response(b"bad", 500), 40),
                 ("body cap", lambda _seq: self.Response(b"x" * (2097152 + 1), 200), 41),
                 ("checksum", lambda seq: self.Response(b"not-a-checksum" if seq == 5 else b"", 200), 42)]
        for name, make_response, serial in cases:
            with self.subTest(name=name):
                writer = self.Writer()
                responses = []
                def fake(_method, _url, _timeout):
                    response = make_response(len(responses) + 1); responses.append(response); return response
                self.assertFalse(CLIENT._run_with_transport(self.issue(serial), fake, writer, lambda: 0))
                self.assertEqual(sum(record["terminal"] for record in writer.records), 1)
                self.assertTrue(writer.records[-1]["terminal"])
                self.assertTrue(all(response.closed for response in responses))

    def test_total_timeout_before_and_after_transport_writes_terminal(self):
        writer = self.Writer(); calls = []
        values = iter((0, 91, 91))
        response = self.Response()
        self.assertFalse(CLIENT._run_with_transport(self.issue(20), lambda *args: calls.append(args) or response, writer, lambda: next(values)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(writer.records[0]["request_attempted"]); self.assertTrue(response.closed)

    def test_http_error_status_body_location_and_date_are_recorded(self):
        import io
        error = CLIENT.urllib.error.HTTPError("https://example.invalid", 302, "redirect", {"Location": "https://elsewhere", "Date": "Wed, 01 Jan 2026 00:00:00 GMT"}, io.BytesIO(b"redirect-body"))
        writer = self.Writer()
        self.assertFalse(CLIENT._run_with_transport(self.issue(22), lambda *_args: (_ for _ in ()).throw(error), writer, lambda: 0))
        record = writer.records[0]
        self.assertEqual(record["status_code"], 302); self.assertEqual(record["response_bytes"], len(b"redirect-body"))
        self.assertIn("Location", record["response_headers"]); self.assertTrue(error.fp is None or error.fp.closed)

    def test_http_error_body_capture_stays_inside_remaining_deadline(self):
        class SlowBody:
            def __init__(self): self.closed = False
            def read(self, _count): raise CLIENT._DeadlineExceeded("slow error body")
            def close(self): self.closed = True
        limits, body, writer = [], SlowBody(), self.Writer()
        class Deadline:
            def __init__(self, limit): limits.append(limit)
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        error = CLIENT.urllib.error.HTTPError("https://example.invalid", 302, "redirect", {"Location": "https://elsewhere"}, body)
        self.assertFalse(CLIENT._run_with_transport(self.issue(23), lambda *_args: (_ for _ in ()).throw(error), writer, lambda: 0, deadline_factory=Deadline))
        self.assertEqual(limits, [20, 20]); self.assertEqual(writer.records[0]["error"], "_DeadlineExceeded")
        self.assertEqual(writer.records[0]["body_capture_state"], "READ_OR_CLOSE_FAILED"); self.assertTrue(body.closed)

    def test_read_failure_is_not_retried_and_still_writes_terminal(self):
        class FailingRead(self.Response):
            def __init__(self):
                super().__init__(); self.read_count = 0
            def read(self, _count):
                self.read_count += 1
                raise OSError("read failure")
        response, writer = FailingRead(), self.Writer()
        self.assertFalse(CLIENT._run_with_transport(self.issue(37), lambda *_args: response, writer, lambda: 0))
        self.assertEqual(response.read_count, 1); self.assertTrue(response.closed)
        self.assertEqual(writer.records[0]["status_code"], 200)
        self.assertEqual(writer.records[0]["record_type"], "TERMINAL")

    def test_posix_deadline_interrupts_a_slow_read_offline(self):
        class SlowRead:
            def read(self, _count): time.sleep(0.05)
        with self.assertRaises(CLIENT._DeadlineExceeded):
            with CLIENT._posix_deadline(0.01): SlowRead().read(1)

    def test_existing_itimer_is_rejected_before_tcp_without_replacement(self):
        previous = CLIENT.signal.setitimer(CLIENT.signal.ITIMER_REAL, 5)
        try:
            with self.assertRaises(CLIENT.ContractError): CLIENT._require_production_alarm_available()
            current = CLIENT.signal.getitimer(CLIENT.signal.ITIMER_REAL)
            self.assertGreater(current[0], 0)
        finally:
            CLIENT.signal.setitimer(CLIENT.signal.ITIMER_REAL, previous[0], previous[1])

    def test_deadline_seam_bounds_slow_read_and_writes_one_terminal(self):
        limits = []
        class Deadline:
            def __init__(self, limit): limits.append(limit)
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        class SlowRead(self.Response):
            def read(self, _count): raise CLIENT._DeadlineExceeded("slow response")
        writer = self.Writer()
        self.assertFalse(CLIENT._run_with_transport(self.issue(38), lambda *_args: SlowRead(), writer, lambda: 0, deadline_factory=Deadline))
        self.assertEqual(limits, [20]); self.assertEqual(len(writer.records), 1)
        self.assertTrue(writer.records[0]["terminal"]); self.assertEqual(writer.records[0]["error"], "_DeadlineExceeded")

    def test_deadline_uses_remaining_total_budget_then_blocks_next_request(self):
        limits, calls, writer = [], [], self.Writer()
        class Deadline:
            def __init__(self, limit): limits.append(limit)
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        class Clock:
            value = 0.0
            def __call__(self): return self.value
        clock = Clock()
        def transport(*args):
            calls.append(args)
            clock.value += 18.75 if len(calls) < 5 else 15
            return self.Response()
        self.assertFalse(CLIENT._run_with_transport(self.issue(39), transport, writer, clock, deadline_factory=Deadline))
        self.assertEqual(limits, [20, 20, 20, 20, 15]); self.assertEqual(len(calls), 5)
        self.assertTrue(writer.records[-1]["request_attempted"])

    def test_evidence_durability_time_is_excluded_from_network_budget(self):
        limits = []
        class Clock:
            value = 0.0
            def __call__(self): return self.value
        clock = Clock()
        class SlowDurabilityWriter(self.Writer):
            def write(inner_self, record):
                super(SlowDurabilityWriter, inner_self).write(record)
                clock.value += 100
        class Deadline:
            def __init__(self, limit): limits.append(limit)
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        writer = SlowDurabilityWriter()
        def transport(_method, url, _timeout):
            body = b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if url.endswith("CHECKSUM") else b""
            return self.Response(body)
        self.assertTrue(CLIENT._run_with_transport(self.issue(46), transport, writer, clock, deadline_factory=Deadline))
        self.assertEqual(limits, [20] * 5)
        self.assertTrue(all(record["cumulative_elapsed_ms"] == 0 for record in writer.records))

    def test_evidence_writer_exclusive_nofollow_partial_write_fsync_and_chain(self):
        path = self.dir / "evidence.jsonl"; writer = CLIENT._EvidenceWriter(path)
        real_write = CLIENT.os.write
        with mock.patch.object(CLIENT.os, "write", side_effect=lambda fd, data: real_write(fd, data[:1])):
            writer.write({"sequence": 1}); writer.write({"sequence": 2})
        writer.close()
        lines = path.read_bytes().splitlines()
        first, second = [json.loads(line) for line in lines]
        self.assertEqual(first["previous_sha256"], "0" * 64)
        self.assertEqual(second["previous_sha256"], hashlib.sha256(lines[0] + b"\n").hexdigest())
        regular = self.dir / "regular.jsonl"; regular.write_text("x")
        for target in (regular, self.dir):
            with self.subTest(target=target):
                with self.assertRaises(CLIENT.ContractError): CLIENT._EvidenceWriter(target).prepare()
        link = self.dir / "link.jsonl"; os.symlink(regular, link)
        with self.assertRaises(CLIENT.ContractError): CLIENT._EvidenceWriter(link).prepare()
        broken = CLIENT._EvidenceWriter(self.dir / "broken.jsonl")
        with mock.patch.object(CLIENT.os, "fsync", side_effect=OSError("fsync")):
            with self.assertRaises(CLIENT.EvidenceDurabilityError): broken.write({"sequence": 1})
        broken.close()

    def test_activation_header_is_first_durable_binding_and_chains_requests(self):
        raw = self.raw_activation(35)
        cap = CLIENT.issue_activation_capability(raw, now=2_000_000_000)
        path = self.dir / "evidence.jsonl"; writer = CLIENT._EvidenceWriter(path)
        writer.write(CLIENT._activation_record(cap, 2_000_000_000))
        def fake(_method, url, _timeout):
            return self.Response(b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if url.endswith("CHECKSUM") else b"")
        self.assertTrue(CLIENT._run_with_transport(cap, fake, writer, lambda: 0))
        writer.close()
        lines = path.read_bytes().splitlines(); records = [json.loads(line) for line in lines]
        self.assertEqual(records[0]["previous_sha256"], "0" * 64)
        self.assertEqual(records[0]["record_type"], "ACTIVATION")
        self.assertEqual(records[0]["bindings"], self.activation(35)["bindings"])
        self.assertEqual(records[0]["activation_sha256"], self.activation(35)["activation_sha256"])
        self.assertEqual(records[0]["activation_raw_physical_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(records[0]["request_plan"], CLIENT._request_plan())
        self.assertEqual(records[1]["previous_sha256"], hashlib.sha256(lines[0] + b"\n").hexdigest())
        self.assertEqual(records[1]["schema_version"], CLIENT.EVIDENCE_SCHEMA_VERSION)

    def test_activation_header_durability_failure_allows_zero_transport(self):
        calls, writes = [], []
        class BrokenWriter:
            def __init__(self, _path): pass
            def prepare(self): pass
            def write(self, record): writes.append(record); raise CLIENT.EvidenceDurabilityError("fsync")
            def close(self): pass
        class Opener:
            def open(self, *_args, **_kwargs): calls.append(True); raise AssertionError("transport")
        cap = self.issue(36)
        with mock.patch.object(CLIENT, "_EvidenceWriter", BrokenWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            with self.assertRaises(CLIENT.EvidenceDurabilityError): CLIENT.run_preflight(cap)
        self.assertEqual(calls, []); self.assertEqual(len(writes), 1)
        with self.assertRaises(PermissionError): CLIENT.run_preflight(cap)

    def test_request_record_durability_failure_stops_transport_without_terminal_retry(self):
        calls, records = [], []
        class BrokenRequestWriter:
            def __init__(self, _path): self.writes = 0
            def prepare(self): pass
            def write(self, record):
                self.writes += 1
                if self.writes == 2: raise CLIENT.EvidenceDurabilityError("request fsync")
                records.append(dict(record))
            def close(self): pass
        class Opener:
            def open(self, *_args, **_kwargs): calls.append(True); return self_response
        self_response = self.Response()
        cap = self.issue(43)
        with mock.patch.object(CLIENT, "_EvidenceWriter", BrokenRequestWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            with self.assertRaises(CLIENT.EvidenceDurabilityError): CLIENT.run_preflight(cap)
        self.assertEqual(len(calls), 1); self.assertEqual([r["record_type"] for r in records], ["ACTIVATION"])
        with self.assertRaises(PermissionError): CLIENT.run_preflight(cap)

    def test_close_failure_is_unsealed_consumed_and_has_no_further_transport(self):
        calls, records = [], []
        class CloseBrokenWriter:
            def __init__(self, _path): pass
            def prepare(self): pass
            def write(self, record): records.append(dict(record))
            def close(self): raise OSError("close")
        class Opener:
            def open(self, request, **_kwargs):
                calls.append(request.full_url)
                body = b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if request.full_url.endswith("CHECKSUM") else b""
                return Har1R2StaticTest.Response(body)
        cap = self.issue(44)
        with mock.patch.object(CLIENT, "_EvidenceWriter", CloseBrokenWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            with self.assertRaises(CLIENT.EvidenceDurabilityError): CLIENT.run_preflight(cap)
        self.assertEqual(len(calls), 5); self.assertTrue(records[-1]["terminal"])
        self.assertTrue(all("sealed" not in record for record in records))
        with self.assertRaises(PermissionError): CLIENT.run_preflight(cap)

    def test_close_failure_after_fsynced_success_or_failure_is_distinct_and_never_sealed(self):
        for serial, status, expected_calls in ((50, 200, 5), (51, 500, 1)):
            with self.subTest(status=status):
                calls, records = [], []
                class CloseBrokenWriter:
                    def __init__(self, _path): pass
                    def prepare(self): pass
                    def write(self, record): records.append(dict(record))
                    def close(self): raise OSError("close")
                class Opener:
                    def open(self, request, **_kwargs):
                        calls.append(request.full_url)
                        body = b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if request.full_url.endswith("CHECKSUM") else b""
                        return Har1R2StaticTest.Response(body, status if len(calls) == 1 else 200)
                cap = self.issue(serial)
                with mock.patch.object(CLIENT, "_EvidenceWriter", CloseBrokenWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
                    with self.assertRaises(CLIENT.EvidenceCloseFailureAfterFsyncError) as raised:
                        CLIENT.run_preflight(cap)
                self.assertEqual(str(raised.exception), "EVIDENCE_CLOSE_FAILURE_AFTER_FSYNC")
                self.assertEqual(raised.exception.external_evidence_state, "REVIEW_REQUIRED_CLOSE_ERROR")
                self.assertEqual(len(calls), expected_calls)
                self.assertTrue(records[-1]["terminal"])
                with self.assertRaises(PermissionError): CLIENT.run_preflight(cap)

    def test_close_success_readback_is_read_only_and_returns_only_sealed_classification(self):
        path = self.dir / "run-preflight.jsonl"
        class TempWriter(CLIENT._EvidenceWriter):
            def __init__(self, _path): super().__init__(path)
        class Opener:
            def open(self, request, **_kwargs):
                body = b"A" * 64 + b"  BTCUSDT-1m-2025-07.zip\n" if request.full_url.endswith("CHECKSUM") else b""
                return Har1R2StaticTest.Response(body)
        cap = self.issue(52)
        with mock.patch.object(CLIENT, "_EvidenceWriter", TempWriter), mock.patch.object(CLIENT, "_build_production_opener", return_value=Opener()):
            result = CLIENT.run_preflight(cap)
        self.assertEqual(result, {"external_evidence_state": "SEALED", "protocol_outcome": "SUCCESS", "terminal_reliable": True})
        with mock.patch.object(CLIENT.os, "write", side_effect=AssertionError("readback wrote")), mock.patch.object(CLIENT.os, "fsync", side_effect=AssertionError("readback fsynced")):
            self.assertEqual(CLIENT._readback_sealed_evidence(path, cap), result)

    def test_readback_rejects_duplicate_nonfinite_truncated_chain_sequence_and_terminal_drift(self):
        cap, path = self.sealed_failure_file(53)
        raw = path.read_bytes()
        first, second = raw.split(b"\n")[:2]
        cases = {
            "duplicate": raw.replace(b'"record_type":"ACTIVATION"', b'"record_type":"ACTIVATION","record_type":"ACTIVATION"', 1),
            "nonfinite": raw.replace(b'"terminal":false', b'"terminal":NaN', 1),
            "truncated": raw[:-1],
            "chain": first + b"\n" + second.replace(hashlib.sha256(first + b"\n").hexdigest().encode("ascii"), b"0" * 64, 1) + b"\n",
            "sequence": raw.replace(b'"sequence":1', b'"sequence":2', 1),
            "terminal-drift": raw + b'{"extra":true}\n',
        }
        for name, tampered in cases.items():
            with self.subTest(name=name):
                target = self.dir / ("tampered-" + name + ".jsonl")
                target.write_bytes(tampered)
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError) as raised:
                    CLIENT._readback_sealed_evidence(target, cap)
                self.assertEqual(raised.exception.external_evidence_state, "UNSEALED_OR_REVIEW_REQUIRED")

    def test_readback_rejects_nonexact_activation_plans_with_recomputed_raw_chain(self):
        cap, path = self.sealed_failure_file(59)
        original = [json.loads(line) for line in path.read_bytes().splitlines()]
        cases = (
            ("top-level-bool", lambda records: records[0]["request_plan"][0].__setitem__("sequence", True)),
            ("binding-float", lambda records: records[0]["bindings"]["request_plan"][3].__setitem__("body_cap_bytes", 0.0)),
            ("binding-extra", lambda records: records[0]["bindings"]["request_plan"][0].__setitem__("extra", "drift")),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                records = copy.deepcopy(original)
                mutate(records)
                raw, previous = b"", "0" * 64
                for record in records:
                    record["previous_sha256"] = previous
                    line = CLIENT._canonical(record) + b"\n"
                    raw += line
                    previous = hashlib.sha256(line).hexdigest()
                target = self.dir / ("readback-nonexact-" + name + ".jsonl")
                target.write_bytes(raw)
                with self.assertRaisesRegex(CLIENT.EvidenceReadbackValidationError, "activation binding drift"):
                    CLIENT._readback_sealed_evidence(target, cap)

    def test_readback_rejects_final_symlink_and_nonregular_targets(self):
        cap, path = self.sealed_failure_file(55)
        directory = self.dir / "readback-directory"
        directory.mkdir()
        symlink = self.dir / "readback-symlink.jsonl"
        os.symlink(path, symlink)
        for target in (symlink, directory):
            with self.subTest(target=target.name):
                with self.assertRaises(CLIENT.EvidenceReadbackValidationError) as raised:
                    CLIENT._readback_sealed_evidence(target, cap)
                self.assertEqual(raised.exception.external_evidence_state, "UNSEALED_OR_REVIEW_REQUIRED")

    def test_terminal_is_a_fsynced_protocol_record_not_a_whole_file_seal(self):
        cap, path = self.sealed_failure_file(54)
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        self.assertTrue(records[-1]["terminal"])
        self.assertEqual(CLIENT._readback_sealed_evidence(path, cap)["external_evidence_state"], "SEALED")
        self.assertNotIn("sealed", records[-1])

    def test_protocol_failure_has_exactly_one_fsynced_terminal(self):
        path = self.dir / "protocol-terminal.jsonl"; writer = CLIENT._EvidenceWriter(path)
        real_fsync = CLIENT.os.fsync
        with mock.patch.object(CLIENT.os, "fsync", wraps=real_fsync) as fsync:
            self.assertFalse(CLIENT._run_with_transport(self.issue(45), lambda *_args: self.Response(b"bad", 500), writer, lambda: 0))
        writer.close()
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        self.assertEqual(fsync.call_count, 1); self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_type"], "TERMINAL"); self.assertTrue(records[0]["terminal"])

    def test_protocol_failure_cumulative_network_time_is_not_double_counted(self):
        class Clock:
            value = 0.0
            def __call__(self): return self.value
        clock, writer = Clock(), self.Writer()
        def transport(*_args):
            clock.value += 3
            return self.Response(b"bad", 500)
        self.assertFalse(CLIENT._run_with_transport(self.issue(47), transport, writer, clock))
        self.assertEqual(writer.records[0]["request_elapsed_ms"], 3000)
        self.assertEqual(writer.records[0]["cumulative_elapsed_ms"], 3000)

    def test_fake_durability_failure_is_not_claimed_sealed(self):
        cap = self.issue(30)
        class BrokenWriter:
            def write(self, _record): raise OSError("fsync")
        with self.assertRaises(CLIENT.EvidenceDurabilityError):
            CLIENT._run_with_transport(cap, lambda *_args: self.Response(status=500), BrokenWriter(), lambda: 0)

    def test_proxy_redirect_cookie_auth_and_no_pre_tcp_transport(self):
        opener = CLIENT._build_production_opener()
        handlers = opener.handlers
        self.assertTrue(any(isinstance(handler, CLIENT._ForcedHttpsProxyHandler) for handler in handlers))
        self.assertFalse(any(isinstance(handler, CLIENT.urllib.request.HTTPCookieProcessor) for handler in handlers))
        self.assertFalse(any("AuthHandler" in type(handler).__name__ for handler in handlers))
        request = CLIENT._production_request("GET", CLIENT.FUTURE_REQUESTS[0][2])
        with mock.patch.object(CLIENT.urllib.request, "proxy_bypass", side_effect=AssertionError("bypass")):
            CLIENT._ForcedHttpsProxyHandler().proxy_open(request, CLIENT.PROXY, "https")
        self.assertEqual(request.host, "127.0.0.1:7897")
        self.assertEqual(request._tunnel_host, "www.binance.com")
        self.assertIsNone(CLIENT._NoRedirect().redirect_request(None, None, None, None, None, None, None))
        bad_cap = self.issue(31, client_hash="0" * 64)
        with mock.patch.object(CLIENT.urllib.request, "build_opener", side_effect=AssertionError("socket/opener")):
            with self.assertRaises(CLIENT.ContractError): CLIENT.run_preflight(bad_cap)
        self.assertFalse((ROOT / "har1r2/evidence.jsonl").exists())

    def test_pre_tcp_identity_accepts_current_files_and_rejects_final_hash_drift(self):
        CLIENT._pre_tcp_recheck(self.issue(32))
        with self.assertRaises(CLIENT.ContractError): CLIENT._pre_tcp_recheck(self.issue(33, test_hash="f" * 64))

    def test_head_nonzero_body_is_terminal_failure(self):
        writer, responses = self.Writer(), []
        def fake(_method, _url, _timeout):
            response = self.Response(b"x" if len(responses) == 3 else b"")
            responses.append(response)
            return response
        self.assertFalse(CLIENT._run_with_transport(self.issue(34), fake, writer, lambda: 0))
        self.assertEqual(writer.records[-1]["sequence"], 4)
        self.assertTrue(writer.records[-1]["terminal"])
        self.assertTrue(all(response.closed for response in responses))

    def test_production_entry_has_no_transport_or_opener_parameter(self):
        self.assertEqual(list(inspect.signature(CLIENT.run_preflight).parameters), ["capability"])
        self.assertFalse((ROOT / "har1r2/evidence.jsonl").exists())

    def test_evidence_writer_rejects_symlink_parent_before_open(self):
        real_parent = self.dir / "real-parent"; real_parent.mkdir()
        symlink_parent = self.dir / "symlink-parent"; os.symlink(real_parent, symlink_parent)
        with self.assertRaises(CLIENT.ContractError): CLIENT._EvidenceWriter(symlink_parent / "evidence.jsonl").prepare()

    def test_frozen_future_request_order_and_caps(self):
        self.assertEqual(CLIENT._request_plan(), [{"sequence": n, "method": method, "url": url, "body_cap_bytes": cap} for n, method, url, cap in CLIENT.FUTURE_REQUESTS])
        self.assertEqual(CLIENT.FUTURE_REQUESTS[3], (4, "HEAD", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip", 0))
        self.assertFalse((ROOT / "har1r2/evidence.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
