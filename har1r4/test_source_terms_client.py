import copy
import hashlib
import importlib.util
import io
import json
import os
import pickle
import socket
import stat
import signal
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = ROOT / "har1r4/source_terms_client.py"

# The tripwire is active before R4 import and therefore before R4 hash-loads R3.
SOCKET_TRIPWIRE = mock.patch.object(
    socket, "socket", side_effect=AssertionError("R4_OFFLINE_TEST_NETWORK_ZERO")
)
SOCKET_TRIPWIRE.start()
SPEC = importlib.util.spec_from_file_location("har1r4_source_terms_client", CLIENT_PATH)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


class Headers:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, name, default=None):
        values = self.values.get(name)
        return default if not values else values[0]

    def get_all(self, name):
        return list(self.values.get(name, []))


class Response:
    def __init__(self, body, url, status=200, content_type="application/json", extra_headers=None):
        self.body, self.url, self.status, self.closed = body, url, status, False
        values = {"Content-Type": [content_type]}
        values.update(extra_headers or {})
        self.headers = Headers(values)

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.url

    def close(self):
        self.closed = True


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class SourceTermsClientTest(unittest.TestCase):
    serial = 0

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.test_root = Path(self.tmp.name)
        self.wall = Clock(2_000_000_000.0)
        self.monotonic = Clock(0.0)
        self._copy_frozen_tree()

    def tearDown(self):
        self.tmp.cleanup()

    def _copy(self, relative, raw=None):
        target = self.test_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes() if raw is None else raw)

    def _copy_frozen_tree(self):
        for relative in (
            CLIENT.ROUTE_PATH,
            CLIENT.PLAN_PATH,
            CLIENT.CONTRACT_PATH,
            "config/sol_decision.har1r3-dual-lane-successor-route.v1.json",
            "config/sol_activation.har1r3-tech-reachability.v1.json",
            "har1r3/technical_client.py",
            "har1r3/technical_evidence.jsonl",
            "config/sol_activation.har1r3-terms-evidence.v1.json",
            "har1r3/terms_evidence_contract.json",
            "har1r3/terms_evidence/manifest.json",
        ):
            self._copy(relative)

    def activation_raw(self, mutate=None, ttl=600):
        type(self).serial += 1
        issued = 1_999_999_900.0 + type(self).serial / 1000.0
        document = {
            "schema_version": "har1r4-source-terms-raw-activation.v1",
            "decision_id": "SOL_HAR1R4_SOURCE_TERMS_RAW_ACTIVATION.v1",
            "permission": "ONE_FOUR_GET_RAW_DOCUMENT_BATCH",
            "issued_at_utc": CLIENT._utc_now(issued),
            "expires_at_utc": CLIENT._utc_now(issued + ttl),
            "bindings": CLIENT._activation_bindings(),
            "canonical_self_digest": {
                "algorithm": "SHA-256_CANONICAL_JSON",
                "digest_field": "activation_sha256",
                "domain_prefix_utf8": "msta-hed/har1r4-source-terms-raw-activation/v1",
            },
        }
        if mutate is not None:
            mutate(document)
        unsigned = copy.deepcopy(document)
        document["activation_sha256"] = hashlib.sha256(
            b"msta-hed/har1r4-source-terms-raw-activation/v1\0"
            + CLIENT._canonical(unsigned)
        ).hexdigest()
        return CLIENT._canonical(document)

    def issue(self, raw=None, write=True):
        raw = self.activation_raw() if raw is None else raw
        capability = CLIENT.issue_activation_capability(raw, now=self.wall())
        if write:
            self._copy(CLIENT.ACTIVATION_PATH, raw)
        return capability

    def documents(self):
        tree_sha = "a" * 40
        repository = {
            "owner": {"login": "binance"},
            "full_name": "binance/binance-public-data",
            "default_branch": "master",
        }
        commit = {"commit": {"tree": {"sha": tree_sha}}}
        tree = {
            "sha": tree_sha,
            "truncated": False,
            "tree": [
                {
                    "path": "README.md",
                    "type": "blob",
                    "sha": CLIENT.SEALED_README_GIT_BLOB_SHA1,
                },
                {"path": "LICENSE", "type": "blob", "sha": "b" * 40},
            ],
        }
        clause = (
            "Effective Date 2026-07-29. These Terms are between the user and "
            "Binance Japan Inc. They are governed by the laws of Japan and the "
            "courts of Tokyo have exclusive jurisdiction. Market data and public "
            "data services may be accessed, downloaded, used, and retained for "
            "research subject to these Terms. "
        )
        terms = ("<html><body><h1>Terms of Use</h1>" + clause * 5 + "</body></html>").encode()
        return [
            CLIENT._canonical(repository),
            CLIENT._canonical(commit),
            CLIENT._canonical(tree),
            terms,
        ]

    def transport(self, bodies=None, statuses=None, extras=None, responses=None):
        bodies = self.documents() if bodies is None else bodies
        statuses = [200] * 4 if statuses is None else statuses
        extras = [{} for _ in range(4)] if extras is None else extras
        calls = []

        def invoke(method, url, timeout, headers):
            sequence = len(calls)
            content_type = "text/html; charset=utf-8" if sequence == 3 else "application/json; charset=utf-8"
            response = Response(
                bodies[sequence], url, statuses[sequence], content_type, extras[sequence]
            )
            calls.append((method, url, timeout, headers, response))
            if responses is not None:
                responses.append(response)
            return response

        return invoke, calls

    def execute_success(self):
        capability = self.issue()
        transport, calls = self.transport()
        result = CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        return result, calls, capability

    def test_static_hash_schema_cross_bindings_and_r3_replay(self):
        route, plan, contract = CLIENT.validate_static_files()
        self.assertEqual(route["r3_sealed_binding"]["technical_evidence"]["cumulative_elapsed_ms"], 2270)
        self.assertEqual(route["r3_sealed_binding"]["technical_evidence"]["total_response_body_bytes"], 5233)
        self.assertEqual(plan["requests"], CLIENT._request_plan())
        self.assertEqual(contract["output_paths"], CLIENT._output_paths())
        facts = CLIENT.replay_r3_sealed_inputs()
        self.assertEqual(facts["readme_bytes"], 5144)
        self.assertEqual(facts["readme_git_blob_sha1"], CLIENT.SEALED_README_GIT_BLOB_SHA1)

    def test_root_readme_is_not_an_input_and_baseline_pre_tcp_passes(self):
        (self.test_root / "README.md").write_bytes(b"arbitrary user working tree content")
        capability = self.issue()
        self.assertTrue(CLIENT._pre_tcp_recheck(capability, self.test_root))
        (self.test_root / "README.md").write_bytes(b"changed again")
        self.assertTrue(CLIENT._pre_tcp_recheck(capability, self.test_root))

    def test_r3_raw_chain_and_rechained_body_tamper_are_rejected(self):
        activation = CLIENT._strict_json(
            (ROOT / "config/sol_activation.har1r3-tech-reachability.v1.json").read_bytes()
        )
        original = (ROOT / "har1r3/technical_evidence.jsonl").read_bytes()
        broken = bytearray(original)
        broken[20] ^= 1
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.validate_r3_evidence_raw(bytes(broken), activation)
        records = [json.loads(line) for line in original.splitlines()]
        records[1]["body_base64"] = base64_value = records[1]["body_base64"][:-4] + "AAAA"
        self.assertIsInstance(base64_value, str)
        raw, previous = b"", "0" * 64
        for record in records:
            record["previous_sha256"] = previous
            line = CLIENT._canonical(record) + b"\n"
            raw += line
            previous = hashlib.sha256(line).hexdigest()
        with self.assertRaises(CLIENT.ContractError):
            CLIENT.validate_r3_evidence_raw(raw, activation)

    def test_activation_file_raw_and_canonical_binding(self):
        raw = self.activation_raw()
        capability = self.issue(raw, write=False)
        other = self.activation_raw()
        self._copy(CLIENT.ACTIVATION_PATH, other)
        with self.assertRaisesRegex(CLIENT.ContractError, "activation raw physical"):
            CLIENT._pre_tcp_recheck(capability, self.test_root)

    def test_activation_strict_types_ttl_and_final_hash(self):
        mutations = (
            lambda document: document["bindings"].__setitem__("requests", []),
            lambda document: document["bindings"]["requests"][0].__setitem__("sequence", True),
            lambda document: document["bindings"].__setitem__("client_physical", "0" * 64),
            lambda document: document.__setitem__("extra", True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                with self.assertRaises(CLIENT.ContractError):
                    CLIENT.issue_activation_capability(
                        self.activation_raw(mutate=mutate), now=self.wall()
                    )
        for ttl in (0, -1, 901):
            with self.subTest(ttl=ttl):
                with self.assertRaises(CLIENT.ContractError):
                    CLIENT.issue_activation_capability(
                        self.activation_raw(ttl=ttl), now=self.wall()
                    )
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b"\xef\xbb\xbf{}", b"\xff"):
            with self.assertRaises(CLIENT.ContractError):
                CLIENT.issue_activation_capability(raw, now=self.wall())

    def test_capability_private_issuer_duplicate_cross_pid_and_single_use(self):
        with self.assertRaises(PermissionError):
            CLIENT._SourceTermsCapability(object(), {}, "x", "y", 0, 1)
        raw = self.activation_raw()
        capability = CLIENT.issue_activation_capability(raw, now=self.wall())
        with self.assertRaises(PermissionError):
            CLIENT.issue_activation_capability(raw, now=self.wall())
        with self.assertRaises(PermissionError):
            copy.copy(capability)
        with self.assertRaises(PermissionError):
            copy.deepcopy(capability)
        with self.assertRaises(PermissionError):
            pickle.dumps(capability)
        capability._pid += 1
        with self.assertRaises(PermissionError):
            CLIENT._consume_capability(capability, self.wall())
        capability._pid = os.getpid()
        CLIENT._consume_capability(capability, self.wall())
        with self.assertRaises(PermissionError):
            CLIENT._consume_capability(capability, self.wall())

    def test_concurrent_consume_allows_exactly_one(self):
        capability = self.issue(write=False)
        results = []

        def consume():
            try:
                CLIENT._consume_capability(capability, self.wall())
                results.append(True)
            except PermissionError:
                results.append(False)

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)

    def test_no_proxy_environment_cannot_bypass_forced_handler(self):
        request = urllib.request.Request(CLIENT.REQUESTS[0][2])
        handler = CLIENT._ForcedHttpsProxyHandler()
        with mock.patch.object(urllib.request, "proxy_bypass", return_value=True):
            self.assertIsNone(handler.proxy_open(request, CLIENT.PROXY, "https"))
        self.assertEqual(request.host, "127.0.0.1:7897")
        self.assertEqual(request.type, "https")
        opener = CLIENT._build_production_opener()
        self.assertFalse(any(item.__class__.__name__ == "HTTPCookieProcessor" for item in opener.handlers))
        self.assertTrue(any(item.__class__.__name__ == "_NoRedirect" for item in opener.handlers))

    def test_exact_headers_and_production_entry_has_no_transport_parameter(self):
        for sequence in range(1, 5):
            request = CLIENT._production_request(sequence)
            actual = {name.lower(): value for name, value in request.header_items()}
            expected = {name.lower(): value for name, value in CLIENT.REQUESTS[sequence - 1][6].items()}
            self.assertEqual(actual, expected)
            self.assertNotIn("cookie", actual)
            self.assertNotIn("authorization", actual)
        self.assertEqual(
            list(__import__("inspect").signature(CLIENT.execute_source_terms_raw).parameters),
            ["capability"],
        )

    def test_79_seconds_leaves_one_second_and_deadline_return_is_failure(self):
        capability = self.issue()
        bodies = self.documents()
        calls = []

        def transport(method, url, timeout, headers):
            sequence = len(calls)
            calls.append(timeout)
            if sequence == 0:
                self.monotonic.value = 79.0
            response = Response(
                bodies[sequence], url,
                content_type="text/html" if sequence == 3 else "application/json",
            )
            return response

        result = CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        # An observed overrun freezes later transport attempts; it is not
        # treated as permission to spend the apparent remaining second.
        self.assertEqual(calls, [20.0])
        self.assertEqual(result["protocol_outcome"], "FAILURE")
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertIn("REQUEST_DEADLINE_EXCEEDED_AFTER_RETURN", records[1]["validation_errors"])
        self.assertTrue(all(record["request_attempted"] is False for record in records[2:5]))

    def test_deadline_factory_receives_absolute_remaining_limits(self):
        capability = self.issue()
        transport, _ = self.transport()
        limits = []

        class Deadline:
            def __init__(self, limit):
                limits.append(limit)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall,
            deadline_factory=Deadline,
        )
        self.assertEqual(limits, [20.0, 20.0, 20.0, 20.0])

    def test_response_is_closed_before_raw_or_jsonl_persistence(self):
        capability = self.issue()
        responses = []
        transport, _ = self.transport(responses=responses)
        original = CLIENT._ExclusiveFile.write_and_seal

        def checking_write(instance, content):
            if instance.relative in CLIENT.RAW_PATHS:
                self.assertTrue(responses[-1].closed)
            return original(instance, content)

        with mock.patch.object(CLIENT._ExclusiveFile, "write_and_seal", checking_write):
            CLIENT._execute_with_transport(
                capability, transport, self.test_root, self.monotonic, self.wall
            )
        self.assertTrue(all(response.closed for response in responses))

    def test_close_failure_never_persists_unconfirmed_response(self):
        capability = self.issue()
        bodies, calls = self.documents(), []

        class CloseFailure(Response):
            def close(self):
                raise RuntimeError("close failed")

        def transport(method, url, timeout, headers):
            sequence = len(calls)
            calls.append(url)
            cls = CloseFailure if sequence == 0 else Response
            return cls(
                bodies[sequence], url,
                content_type="text/html" if sequence == 3 else "application/json",
            )

        CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        self.assertEqual(len(calls), 4)
        self.assertFalse((self.test_root / CLIENT.RAW_PATHS[0]).exists())
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertEqual(records[1]["error"], "RuntimeError")

    def test_end_to_end_raw_jsonl_manifest_create_once_and_license_fact(self):
        result, calls, capability = self.execute_success()
        self.assertEqual(result["external_evidence_state"], "SEALED")
        self.assertEqual(result["protocol_outcome"], "SUCCESS")
        self.assertEqual(len(calls), 4)
        for relative, expected in zip(CLIENT.RAW_PATHS, self.documents()):
            path = self.test_root / relative
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        records = CLIENT._validate_evidence_readback(self.test_root, capability, "SUCCESS")
        self.assertEqual([record["record_type"] for record in records], [
            "ACTIVATION", "REQUEST", "REQUEST", "REQUEST", "REQUEST", "AGGREGATE_TERMINAL"
        ])
        manifest_raw = (self.test_root / CLIENT.MANIFEST_PATH).read_bytes()
        manifest = CLIENT._strict_json(manifest_raw)
        self.assertEqual(
            CLIENT._canonical_digest(
                manifest, "manifest_sha256",
                "msta-hed/har1r4-source-terms-manifest/v1",
            ),
            result["manifest_sha256"],
        )
        self.assertTrue(manifest["repository_facts"]["license_exists"])
        self.assertEqual(
            manifest["repository_facts"]["license_disposition"],
            "EXISTENCE_FACT_ONLY_NOT_AUTHORITY",
        )
        self.assertFalse(manifest["legal_conclusion"])
        with self.assertRaises(CLIENT.ContractError):
            CLIENT._pre_tcp_recheck(capability, self.test_root)

    def test_http_3xx_location_403_429_raw_persist_and_continue(self):
        capability = self.issue()
        statuses = [302, 403, 429, 200]
        extras = [
            {"Location": ["https://example.invalid/next"], "Set-Cookie": ["a=b"]},
            {"Set-Cookie": ["c=d"]},
            {},
            {},
        ]
        transport, calls = self.transport(statuses=statuses, extras=extras)
        result = CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["protocol_outcome"], "FAILURE")
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertEqual([record["status_code"] for record in records[1:5]], statuses)
        self.assertEqual(records[1]["location"], ["https://example.invalid/next"])
        self.assertEqual(records[1]["set_cookie"], ["a=b"])
        self.assertTrue(all(record["set_cookie_reused"] is False for record in records[1:5]))
        for relative in CLIENT.RAW_PATHS:
            self.assertTrue((self.test_root / relative).is_file())

    def test_real_http_error_object_is_persisted_not_followed(self):
        capability = self.issue()
        bodies = self.documents()
        calls = []

        def transport(method, url, timeout, headers):
            sequence = len(calls)
            calls.append(url)
            if sequence == 0:
                headers_obj = Message()
                headers_obj["Content-Type"] = "application/json"
                headers_obj["Location"] = "https://example.invalid/no-follow"
                return (_ for _ in ()).throw(
                    urllib.error.HTTPError(
                        url, 302, "Found", headers_obj, io.BytesIO(bodies[0])
                    )
                )
            return Response(
                bodies[sequence], url,
                content_type="text/html" if sequence == 3 else "application/json",
            )

        CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertEqual(records[1]["status_code"], 302)
        self.assertEqual(records[1]["location"], ["https://example.invalid/no-follow"])
        self.assertEqual(len(calls), 4)

    def test_durability_failure_stops_all_remaining_network(self):
        capability = self.issue()
        transport, calls = self.transport()
        original = CLIENT._ExclusiveFile.write_and_seal
        failed = {"done": False}

        def fail_first_raw(instance, content):
            if instance.relative in CLIENT.RAW_PATHS and not failed["done"]:
                failed["done"] = True
                raise CLIENT.EvidenceDurabilityError("injected")
            return original(instance, content)

        with mock.patch.object(CLIENT._ExclusiveFile, "write_and_seal", fail_first_raw):
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                CLIENT._execute_with_transport(
                    capability, transport, self.test_root, self.monotonic, self.wall
                )
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.test_root / CLIENT.MANIFEST_PATH).exists())

    def test_parent_symlink_is_rejected(self):
        capability = self.issue()
        outside = self.test_root / "outside"
        outside.mkdir()
        evidence = self.test_root / "har1r4/evidence"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(outside, evidence)
        with self.assertRaises(CLIENT.ContractError):
            CLIENT._pre_tcp_recheck(capability, self.test_root)

    def test_partial_write_loop_and_exclusive_readback(self):
        target = "har1r4/evidence/raw/partial.bin"
        real_write = CLIENT.os.write

        def one_byte(fd, data):
            return real_write(fd, data[:1])

        with mock.patch.object(CLIENT.os, "write", side_effect=one_byte):
            CLIENT._ExclusiveFile(self.test_root, target).write_and_seal(b"partial-write")
        self.assertEqual((self.test_root / target).read_bytes(), b"partial-write")
        with self.assertRaises(CLIENT.EvidenceDurabilityError):
            CLIENT._ExclusiveFile(self.test_root, target).write_and_seal(b"overwrite")

    def test_readback_rejects_rechained_tamper(self):
        _, _, capability = self.execute_success()
        evidence = self.test_root / CLIENT.EVIDENCE_PATH
        records = [json.loads(line) for line in evidence.read_bytes().splitlines()]
        records[1]["outcome"] = "FAILURE"
        raw, previous = b"", "0" * 64
        for record in records:
            record["previous_sha256"] = previous
            line = CLIENT._canonical(record) + b"\n"
            raw += line
            previous = hashlib.sha256(line).hexdigest()
        evidence.write_bytes(raw)
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)

    def test_available_at_is_max_of_three_local_clocks_only(self):
        capability = self.issue()
        transport, _ = self.transport(
            extras=[{"Date": ["Thu, 01 Jan 1970 00:00:00 GMT"], "Last-Modified": ["future"]}, {}, {}, {}]
        )

        class AdvancingWall:
            value = 2_000_000_000.0

            def __call__(self):
                result = self.value
                self.value += 0.001
                return result

        wall = AdvancingWall()
        CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, wall
        )
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        for record in records[1:5]:
            expected = max(
                record["received_at_utc"],
                record["persisted_at_utc"],
                record["admitted_at_utc"],
            )
            self.assertEqual(record["available_at_utc"], expected)

    def test_terms_empty_challenge_spa_short_spoof_and_missing_dimensions_denied(self):
        short_spoof = (
            b"<html>Effective Date 2026-07-29 Binance Japan Inc governed by laws "
            b"of Japan market data download.</html>"
        )
        long_missing_data = (
            "<html><body>Effective Date 2026-07-29. Binance Japan Inc. "
            "Governed by the laws of Japan and courts of Tokyo. "
            + "General account services clause. " * 30
            + "</body></html>"
        ).encode()
        cases = (
            b"",
            b"<html>captcha verify you are human</html>",
            b'<html><div id="root"></div><script src="app.js"></script></html>',
            short_spoof,
            long_missing_data,
        )
        for body in cases:
            with self.subTest(body=body[:30]):
                self.assertEqual(
                    CLIENT.validate_terms_raw(body), "WAIT_DATA_TERMS_D0_DENIED"
                )
        self.assertEqual(
            CLIENT.validate_terms_raw(self.documents()[3]),
            "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW",
        )

    def test_repository_mismatch_tree_truncation_and_license_only_fact(self):
        repo, commit, tree, _ = self.documents()
        state, facts = CLIENT.validate_repository_documents(repo, commit, tree)
        self.assertEqual(state, "SOURCE_IDENTITY_CANDIDATE_VALIDATED")
        self.assertTrue(facts["license_exists"])
        self.assertNotIn("permission", facts)
        document = json.loads(tree)
        document["truncated"] = True
        self.assertEqual(
            CLIENT.validate_repository_documents(
                repo, commit, CLIENT._canonical(document)
            )[0],
            "WAIT_DATA_SOURCE_CONTRACT_MISMATCH",
        )

    def test_repository_boolean_shapes_seal_failure_without_crash(self):
        bodies = self.documents()
        bodies[0] = CLIENT._canonical({"owner": True, "full_name": "binance/binance-public-data", "default_branch": "master"})
        bodies[1] = CLIENT._canonical({"commit": True})
        capability = self.issue()
        transport, calls = self.transport(bodies=bodies)
        result = CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["external_evidence_state"], "SEALED")
        self.assertEqual(result["protocol_outcome"], "FAILURE")
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertEqual(len(records), 6)
        self.assertEqual(records[-1]["repository_state"], "WAIT_DATA_SOURCE_CONTRACT_MISMATCH")
        manifest = CLIENT._strict_json((self.test_root / CLIENT.MANIFEST_PATH).read_bytes())
        self.assertIsNone(manifest["repository_facts"])
        self.assertFalse(manifest["legal_conclusion"])
        self.assertEqual(manifest["aggregate_outcome"], "FAILURE")
        self.assertTrue(all((self.test_root / path).is_file() for path in CLIENT.RAW_PATHS))

    def test_repository_validator_is_total_over_malformed_shape_matrix(self):
        repo_raw, commit_raw, tree_raw, _ = self.documents()
        repo = json.loads(repo_raw)
        commit = json.loads(commit_raw)
        tree = json.loads(tree_raw)
        cases = []
        for value in (None, True, [], "owner", 1):
            changed = copy.deepcopy(repo); changed["owner"] = value
            cases.append((changed, commit, tree))
        for value in (None, True, [], "commit", 1):
            changed = copy.deepcopy(commit); changed["commit"] = value
            cases.append((repo, changed, tree))
        for value in (None, True, [], "tree", 1):
            changed = copy.deepcopy(commit); changed["commit"]["tree"] = value
            cases.append((repo, changed, tree))
        for value in (0, 1, "false", None, True):
            changed = copy.deepcopy(tree); changed["truncated"] = value
            cases.append((repo, commit, changed))
        for value in (None, True, {}, "entries", 1):
            changed = copy.deepcopy(tree); changed["tree"] = value
            cases.append((repo, commit, changed))
        for value in (None, True, "entry", 1, []):
            changed = copy.deepcopy(tree); changed["tree"] = [value]
            cases.append((repo, commit, changed))
        mutations = (
            lambda entry: entry.__setitem__("path", True),
            lambda entry: entry.__setitem__("type", None),
            lambda entry: entry.__setitem__("sha", "A" * 40),
            lambda entry: entry.__setitem__("sha", "a" * 39),
            lambda entry: entry.__setitem__("type", "tree"),
        )
        for mutate in mutations:
            changed = copy.deepcopy(tree); mutate(changed["tree"][0])
            cases.append((repo, commit, changed))
        for abnormal in (
            tree["tree"] + [copy.deepcopy(tree["tree"][0])],
            tree["tree"] + [copy.deepcopy(tree["tree"][1])],
            [tree["tree"][0], {"path": "LICENSE", "type": "tree", "sha": "b" * 40}],
        ):
            changed = copy.deepcopy(tree); changed["tree"] = abnormal
            cases.append((repo, commit, changed))
        raw_cases = [(b"{", commit_raw, tree_raw)]
        for root in (None, True, [], "root", 1):
            raw_cases.append((CLIENT._canonical(root), commit_raw, tree_raw))
            raw_cases.append((repo_raw, CLIENT._canonical(root), tree_raw))
            raw_cases.append((repo_raw, commit_raw, CLIENT._canonical(root)))
        for left, middle, right in cases:
            raw_cases.append((CLIENT._canonical(left), CLIENT._canonical(middle), CLIENT._canonical(right)))
        for candidate in raw_cases:
            with self.subTest(candidate=tuple(part[:12] for part in candidate)):
                self.assertEqual(
                    CLIENT.validate_repository_documents(*candidate),
                    ("WAIT_DATA_SOURCE_CONTRACT_MISMATCH", None),
                )

    def _rechain(self, records):
        payload, previous = b"", "0" * 64
        for record in records:
            record["previous_sha256"] = previous
            line = CLIENT._canonical(record) + b"\n"
            payload += line
            previous = hashlib.sha256(line).hexdigest()
        (self.test_root / CLIENT.EVIDENCE_PATH).write_bytes(payload)

    def test_live_observation_rejects_rechained_http_metadata(self):
        _, _, capability = self.execute_success()
        records = [json.loads(line) for line in (self.test_root / CLIENT.EVIDENCE_PATH).read_bytes().splitlines()]
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        records[1]["status_code"] = 503
        records[1]["validation_errors"] = ["HTTP_STATUS"]
        records[1]["outcome"] = "FAILURE"
        records[-1]["request_results"][0]["outcome"] = "FAILURE"
        records[-1]["successful_requests"] = 3
        records[-1]["failed_requests"] = 1
        records[-1]["outcome"] = "FAILURE"
        self._rechain(records)
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability, observations=observations)

    def test_raw_presence_and_captcha_reclassification_are_rejected(self):
        _, _, capability = self.execute_success()
        terms = self.test_root / CLIENT.RAW_PATHS[3]
        terms.write_bytes(b"<html>captcha verify you are human</html>")
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)
        terms.unlink()
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)

    def test_readback_rejects_elapsed_and_timestamp_rechain(self):
        _, _, capability = self.execute_success()
        records = [json.loads(line) for line in (self.test_root / CLIENT.EVIDENCE_PATH).read_bytes().splitlines()]
        records[1]["request_elapsed_ms"] = 400000
        records[1]["cumulative_network_read_elapsed_ms"] = 400000
        for record in records[2:5]:
            record["cumulative_network_read_elapsed_ms"] = 400000
        records[-1]["cumulative_network_read_elapsed_ms"] = 400000
        self._rechain(records)
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)

    def test_production_alarm_preflight_has_no_opener_or_output_mutation(self):
        project_outputs = (
            CLIENT.ACTIVATION_PATH,
            CLIENT.EVIDENCE_PATH,
            CLIENT.MANIFEST_PATH,
            *CLIENT.RAW_PATHS,
        )
        before = {
            relative: (ROOT / relative).read_bytes() if (ROOT / relative).exists() else None
            for relative in project_outputs
        }
        capability = self.issue(write=False)
        with mock.patch.object(CLIENT.R3_SAFETY, "_require_production_alarm_available", side_effect=RuntimeError("alarm")), mock.patch.object(CLIENT, "_build_production_opener") as opener:
            with self.assertRaises(RuntimeError):
                CLIENT.execute_source_terms_raw(capability)
        opener.assert_not_called()
        after = {
            relative: (ROOT / relative).read_bytes() if (ROOT / relative).exists() else None
            for relative in project_outputs
        }
        self.assertEqual(before, after)

    def test_resigned_manifest_cannot_grant_legal_or_repository_state(self):
        _, _, capability = self.execute_success()
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        path = self.test_root / CLIENT.MANIFEST_PATH
        document = json.loads(path.read_bytes())
        document["legal_conclusion"] = True
        document["repository_state"] = "ATTESTED_PERMISSION_GRANTED"
        unsigned = dict(document)
        unsigned.pop("manifest_sha256")
        document["manifest_sha256"] = hashlib.sha256(
            b"msta-hed/har1r4-source-terms-manifest/v1\0" + CLIENT._canonical(unsigned)
        ).hexdigest()
        path.write_bytes(CLIENT._canonical(document))
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_manifest_readback(self.test_root, capability, observations)

    def test_activation_write_failure_closes_writer_before_transport(self):
        capability = self.issue()
        transport, calls = self.transport()
        writer = CLIENT._EvidenceWriter(self.test_root, "har1r4/evidence/prepare.jsonl")
        with mock.patch.object(writer, "write", side_effect=CLIENT.EvidenceDurabilityError("first write")), mock.patch.object(writer, "abort", wraps=writer.abort) as abort:
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                CLIENT._execute_with_transport(
                    capability, transport, self.test_root, self.monotonic, self.wall,
                    evidence_writer_factory=lambda _root: writer,
                )
        abort.assert_called_once()
        self.assertEqual(calls, [])
        self.assertIsNone(writer.fd)
        self.assertIsNone(writer.parent_fd)

    def test_manifest_whitespace_and_current_raw_state_are_rejected(self):
        _, _, capability = self.execute_success()
        path = self.test_root / CLIENT.MANIFEST_PATH
        path.write_bytes(path.read_bytes() + b"\n")
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_manifest_readback(self.test_root, capability, observations)

    def test_manifest_requires_live_observations_and_accepts_exact_ledger(self):
        _, _, capability = self.execute_success()
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_manifest_readback(self.test_root, capability, None)
        manifest, replayed = CLIENT._validate_manifest_readback(
            self.test_root, capability, observations
        )
        self.assertEqual(manifest["aggregate_outcome"], "SUCCESS")
        self.assertEqual(replayed[-1]["outcome"], "SUCCESS")

    def test_noncanonical_jsonl_rechain_is_rejected(self):
        _, _, capability = self.execute_success()
        records = [json.loads(line) for line in (self.test_root / CLIENT.EVIDENCE_PATH).read_bytes().splitlines()]
        payload, previous = b"", "0" * 64
        for record in records:
            record["previous_sha256"] = previous
            line = b" " + CLIENT._canonical(record)
            payload += line + b"\n"
            previous = hashlib.sha256(line + b"\n").hexdigest()
        (self.test_root / CLIENT.EVIDENCE_PATH).write_bytes(payload)
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)

    def test_actual_deadline_exception_latches_prior_records(self):
        capability = self.issue()
        calls = []
        def transport(*_args):
            calls.append(True)
            raise CLIENT.R3_SAFETY.R2_SAFETY._DeadlineExceeded("deadline")
        result = CLIENT._execute_with_transport(
            capability, transport, self.test_root, self.monotonic, self.wall
        )
        self.assertEqual(result["protocol_outcome"], "FAILURE")
        self.assertEqual(len(calls), 1)
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        self.assertEqual(records[1]["error"], "REQUEST_DEADLINE_EXCEEDED")
        self.assertTrue(all(record["error"] == "PRIOR_REQUEST_DEADLINE_EXCEEDED" for record in records[2:5]))

    def test_guard_exit_failure_stops_before_transport_and_manifest(self):
        capability = self.issue()
        transport, calls = self.transport()
        class ExitFailure:
            def __enter__(self): return self
            def __exit__(self, *_args): raise RuntimeError("guard exit")
        with self.assertRaises(RuntimeError):
            CLIENT._execute_with_transport(
                capability, transport, self.test_root, self.monotonic, self.wall,
                deadline_factory=lambda _timeout: ExitFailure(),
            )
        self.assertEqual(len(calls), 1)
        self.assertFalse(any((self.test_root / relative).exists() for relative in CLIENT.RAW_PATHS))
        self.assertFalse((self.test_root / CLIENT.MANIFEST_PATH).exists())

    def test_same_classification_different_raw_bytes_rejected_by_live_ledger(self):
        _, _, capability = self.execute_success()
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        terms_path = self.test_root / CLIENT.RAW_PATHS[3]
        terms_path.write_bytes(terms_path.read_bytes().replace(b"Terms of Use", b"Terms of Use Updated"))
        self.assertEqual(CLIENT.validate_terms_raw(terms_path.read_bytes()), "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW")
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_manifest_readback(self.test_root, capability, observations)

    def test_unlatched_prior_and_total_markers_are_rejected(self):
        for marker in ("PRIOR_REQUEST_DEADLINE_EXCEEDED", "TOTAL_NETWORK_READ_BUDGET_EXHAUSTED"):
            with self.subTest(marker=marker):
                if (self.test_root / CLIENT.EVIDENCE_PATH).exists():
                    self.tmp.cleanup()
                    self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
                    self.test_root = Path(self.tmp.name)
                    self._copy_frozen_tree()
                capability = self.issue()
                bodies, count = self.documents(), {"value": 0}
                def transport(_method, url, _timeout, _headers):
                    index = count["value"]; count["value"] += 1
                    if index == 0:
                        raise OSError("ordinary failure")
                    return Response(bodies[index], url, content_type="text/html" if index == 3 else "application/json")
                CLIENT._execute_with_transport(capability, transport, self.test_root, self.monotonic, self.wall)
                records = [json.loads(line) for line in (self.test_root / CLIENT.EVIDENCE_PATH).read_bytes().splitlines()]
                for key in ("final_url", "validation_errors", "status_code", "content_type", "location", "set_cookie", "set_cookie_reused", "response_bytes", "body_sha256"):
                    records[2].pop(key)
                records[2].update({"request_attempted": False, "outcome": "FAILURE", "error": marker, "request_elapsed_ms": 0, "cumulative_network_read_elapsed_ms": 0, "raw_path": None})
                (self.test_root / CLIENT.RAW_PATHS[1]).unlink()
                self._rechain(records)
                with self.assertRaises(CLIENT.EvidenceReadbackError):
                    CLIENT._validate_evidence_readback(self.test_root, capability)

        # Restore a valid run, then change raw terms after the evidence replay;
        # no re-signed manifest can turn a captcha into acceptable terms text.
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.test_root = Path(self.tmp.name)
        self._copy_frozen_tree()
        _, _, capability = self.execute_success()
        records = CLIENT._validate_evidence_readback(self.test_root, capability)
        observations = [CLIENT._request_observation(record) for record in records[1:5]]
        (self.test_root / CLIENT.RAW_PATHS[3]).write_bytes(b"<html>captcha</html>")
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_manifest_readback(self.test_root, capability, observations)

    def test_deadline_guard_entry_failure_is_not_transport_failure(self):
        capability = self.issue()
        transport, calls = self.transport()

        class BrokenGuard:
            def __enter__(self):
                raise RuntimeError("guard entry")
            def __exit__(self, *_args):
                return False

        with self.assertRaises(RuntimeError):
            CLIENT._execute_with_transport(
                capability, transport, self.test_root, self.monotonic, self.wall,
                deadline_factory=lambda _timeout: BrokenGuard(),
            )
        self.assertEqual(calls, [])
        self.assertTrue((self.test_root / CLIENT.EVIDENCE_PATH).exists())
        self.assertFalse(any((self.test_root / relative).exists() for relative in CLIENT.RAW_PATHS))
        self.assertFalse((self.test_root / CLIENT.MANIFEST_PATH).exists())

    def test_rechained_boolean_scalars_are_rejected(self):
        _, _, capability = self.execute_success()
        records = [json.loads(line) for line in (self.test_root / CLIENT.EVIDENCE_PATH).read_bytes().splitlines()]
        records[1]["sequence"] = True
        self._rechain(records)
        with self.assertRaises(CLIENT.EvidenceReadbackError):
            CLIENT._validate_evidence_readback(self.test_root, capability)

    def test_actual_production_alarm_blocks_nonmain_and_existing_timer(self):
        errors = []
        raw = self.activation_raw()
        capability = CLIENT.issue_activation_capability(raw, now=self.wall())
        with mock.patch.object(CLIENT, "_build_production_opener") as opener:
            thread = threading.Thread(target=lambda: errors.append(self._production_error(capability)))
            thread.start(); thread.join()
            self.assertTrue(errors and errors[0] is not None)
            opener.assert_not_called()
        raw = self.activation_raw()
        capability = CLIENT.issue_activation_capability(raw, now=self.wall())
        try:
            signal.setitimer(signal.ITIMER_REAL, 1.0)
            with mock.patch.object(CLIENT, "_build_production_opener") as opener:
                with self.assertRaises(Exception):
                    CLIENT.execute_source_terms_raw(capability)
                opener.assert_not_called()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)

    def test_writer_open_write_fsync_and_close_failures_release_descriptors(self):
        # Open/parent-fsync failure: prepare's own abort closes every acquired fd.
        writer = CLIENT._EvidenceWriter(self.test_root, "har1r4/evidence/close.jsonl")
        with mock.patch.object(CLIENT.os, "fsync", side_effect=OSError("fsync")):
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                writer.prepare()
        self.assertIsNone(writer.fd); self.assertIsNone(writer.parent_fd)

        # Write failure is cleaned by the execution-level abort path.
        capability = self.issue()
        writer = CLIENT._EvidenceWriter(self.test_root)
        transport, calls = self.transport()
        with mock.patch.object(CLIENT, "_write_all", side_effect=OSError("write")):
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                CLIENT._execute_with_transport(capability, transport, self.test_root, self.monotonic, self.wall, evidence_writer_factory=lambda _root: writer)
        self.assertEqual(calls, []); self.assertIsNone(writer.fd); self.assertIsNone(writer.parent_fd)

        writer = CLIENT._EvidenceWriter(self.test_root, "har1r4/evidence/close-final.jsonl")
        writer.prepare(); writer.write({"probe": "close"})
        real_close, failed = CLIENT.os.close, {"value": False}
        def fail_once(fd):
            if fd == writer.fd and not failed["value"]:
                failed["value"] = True
                raise OSError("close")
            return real_close(fd)
        with mock.patch.object(CLIENT.os, "close", side_effect=fail_once):
            with self.assertRaises(CLIENT.EvidenceDurabilityError):
                writer.close()
        self.assertIsNone(writer.fd); self.assertIsNone(writer.parent_fd)

    @staticmethod
    def _production_error(capability):
        try:
            CLIENT.execute_source_terms_raw(capability)
        except Exception as exc:
            return exc
        return None

    def test_project_completed_outputs_preserve_explicit_failure_state(self):
        self.assertTrue((ROOT / CLIENT.ACTIVATION_PATH).is_file())
        self.assertTrue((ROOT / CLIENT.EVIDENCE_PATH).is_file())
        self.assertTrue((ROOT / CLIENT.MANIFEST_PATH).is_file())
        self.assertTrue(all((ROOT / relative).is_file() for relative in CLIENT.RAW_PATHS))
        manifest = json.loads((ROOT / CLIENT.MANIFEST_PATH).read_bytes())
        self.assertEqual(manifest["aggregate_outcome"], "FAILURE")
        self.assertEqual(manifest["repository_state"], "WAIT_DATA_SOURCE_CONTRACT_MISMATCH")
        self.assertEqual(manifest["terms_state"], "WAIT_DATA_TERMS_D0_DENIED")
        self.assertFalse(manifest["legal_conclusion"])


if __name__ == "__main__":
    unittest.main()
