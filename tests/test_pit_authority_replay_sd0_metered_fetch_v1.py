"""Offline adversarial tests for the checked-in SD0 metered-fetch contract.

These tests never use the real workspace as an output root, never open a real
socket, and do not access Application Support.  The only source files read are
the checked-in plan/contract needed to exercise their real closed schemas.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import http.client
import inspect
import io
import json
import os
import shutil
import socket
import ssl
import tempfile
import threading
import unittest
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from trade_system import pit_authority_replay_sd0_metered_fetch_v1 as sd0


REPOSITORY = Path(__file__).resolve().parents[1]
PLAN_PATH = REPOSITORY / "config/pit_authority_replay.sd0_request_plan.v1.json"
CONTRACT_PATH = REPOSITORY / "config/pit_authority_replay.sd0_measurement_contract.v1.json"
ROUTE_PATH = REPOSITORY / "config/sol_decision.research-system-pit-authority-replay-sd0-d0-phased-route.v1.json"
TEST_EVIDENCE = {"command": "offline unittest", "result": "PASS", "sha256": "a" * 64}


def workspace_output_snapshot(paths: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
    """Capture path state without assuming later-stage evidence is absent."""
    rows = []
    for relative in paths:
        path = REPOSITORY / relative
        if path.is_symlink():
            rows.append((relative, "SYMLINK", os.readlink(path)))
        elif path.is_file():
            rows.append((relative, "FILE", hashlib.sha256(path.read_bytes()).hexdigest()))
        elif path.is_dir():
            rows.append((relative, "DIRECTORY", ""))
        else:
            rows.append((relative, "ABSENT", ""))
    return tuple(rows)


def http_response(
    *,
    status: int = 200,
    content_type: str = "text/plain",
    body: bytes = b"",
    declared_length: int | None = None,
    headers: tuple[tuple[str, str], ...] = (),
) -> sd0.HttpResponse:
    return sd0.HttpResponse(
        status,
        (("Content-Type", content_type), ("Content-Length", str(len(body) if declared_length is None else declared_length))) + headers,
        body,
    )


class SD0MeteredFetchAdversarialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        original_plan = sd0._strict_json(PLAN_PATH.read_bytes())
        self.specs = sd0._validate_plan(original_plan)
        self.plan = copy.deepcopy(original_plan)
        self.plan["route_binding"]["cwd"] = str(self.root.resolve())
        self.plan["plan_sha256"] = sd0._self("pitar1/sd0-request-plan/v1",self.plan,"plan_sha256")
        self.contract = sd0._strict_json(CONTRACT_PATH.read_bytes())
        self.route = sd0._strict_json(ROUTE_PATH.read_bytes())
        self.route["route_identity"]["workspace"] = str(self.root.resolve())
        self.route["decision_sha256"] = sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-d0-phased-route/v1",self.route,"decision_sha256")
        # The authority-hash preflight has its own adversarial tests.  Runtime
        # tests use the real artifact schemas while avoiding hash preimages.
        self.runtime_contract = copy.deepcopy(self.contract)
        self.runtime_contract["authority_bindings"] = []
        with sd0._CAPABILITY_LOCK:
            sd0._READY.clear()
            sd0._CAPABILITIES.clear()
        self._fixture_capability: sd0._ActivationCapability | None = None
        self._activation_counter = 0
        self._authority_counter = 0
        for relative in (
            sd0.R3_DECISION_PATH, sd0.R4_DECISION_PATH, sd0.R5_DECISION_PATH, sd0.R6_DECISION_PATH,
            sd0.R6_COMPLETION_PATH, sd0.R7_DECISION_PATH, sd0.R7_COMPLETION_PATH, sd0.R8_DECISION_PATH,
            sd0.STATIC_PATHS[3], sd0.STATIC_PATHS[4],
        ):
            target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY / relative).read_bytes())

    def tearDown(self) -> None:
        with sd0._CAPABILITY_LOCK:
            sd0._READY.clear()
            sd0._CAPABILITIES.clear()
        self.tempdir.cleanup()

    def materialize_static_inputs(self) -> None:
        for rel in sd0.STATIC_PATHS:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel.endswith("measurement_contract.v1.json"): path.write_bytes(CONTRACT_PATH.read_bytes())
            elif rel.endswith("request_plan.v1.json"): path.write_bytes(sd0._canon(self.plan))
            else: path.write_bytes(b"offline static input\n")
        route=self.root/self.plan["route_binding"]["decision_path"]; route.parent.mkdir(parents=True,exist_ok=True); route.write_bytes(sd0._canon(self.route))

    def materialize_empty_output_parents(self) -> None:
        for rel in sd0.NETWORK_PATHS + (sd0.PREFLIGHT_PATH,):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)

    def client_context(self, *, contract: dict[str, object] | None = None):
        stack = ExitStack()
        stack.enter_context(patch.multiple(
            sd0,
            WORKSPACE=str(self.root),
            BRANCH=self.plan["route_binding"]["branch"],
            HEAD=self.plan["route_binding"]["head"],
            ROUTE_BINDING=self.plan["route_binding"],
            ROUTE_DECISION_PHYSICAL_SHA256=sd0._sha(sd0._canon(self.route)),
            ROUTE_DECISION_CANONICAL_SHA256=self.route["decision_sha256"],
            PLAN_PHYSICAL_SHA256=sd0._sha(sd0._canon(self.plan)),
            PLAN_CANONICAL_SHA256=self.plan["plan_sha256"],
            _load=lambda _safe: (contract or self.runtime_contract, self.plan, self.specs),
            _git=lambda _root, *args: self.plan["route_binding"]["branch"] if args[0] == "branch" else self.plan["route_binding"]["head"],
            _verify_production_suspension_gate=lambda _root: None,
        ))
        real_session_for = sd0._session_for
        def explicit_fixture_capability(capability, root_path, expected_state, next_state):
            if capability is None:
                if expected_state == "MINTED":
                    self._fixture_capability = self._mint_r8(self.root)
                capability = self._fixture_capability
            return real_session_for(capability, root_path, expected_state, next_state)
        stack.enter_context(patch.object(sd0, "_session_for", side_effect=explicit_fixture_capability))
        return stack

    def ready_preflight(self) -> sd0.ReadyPreflight:
        self.materialize_static_inputs()
        self.materialize_empty_output_parents()
        with self.client_context(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=2**63)):
            ready = sd0.preflight(self.root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: True)
        self.assertIsInstance(ready, sd0.ReadyPreflight)
        return ready

    def persist_ready(self, ready: sd0.ReadyPreflight) -> None:
        with self.client_context():
            sd0.persist_ready(self.root, ready)

    def assert_route_failure_matrix(self) -> None:
        variants=("missing","directory","symlink","unreadable","bytes","canonical","id","state","route_id","workspace","branch","head")
        for variant in variants:
            self.tearDown(); self.setUp(); self.materialize_static_inputs(); self.materialize_empty_output_parents(); route=self.root/self.plan["route_binding"]["decision_path"]; restore=None
            if variant=="missing": route.unlink()
            elif variant=="directory": route.unlink(); route.mkdir()
            elif variant=="symlink": sibling=self.root/"route-real.json"; sibling.write_bytes(route.read_bytes()); route.unlink(); os.symlink(sibling,route)
            elif variant=="unreadable": restore=route.stat().st_mode; route.chmod(0)
            elif variant=="bytes": route.write_bytes(b"{}")
            else:
                raw=copy.deepcopy(self.route)
                if variant=="canonical": raw["decision_sha256"]="0"*64
                elif variant=="id": raw["decision_id"]="bad"
                elif variant=="state": raw["decision_state"]="bad"
                elif variant=="route_id": raw["route_identity"]["route_id"]="bad"
                elif variant=="workspace": raw["route_identity"]["workspace"]="bad"
                elif variant=="branch": raw["route_identity"]["branch"]="bad"
                elif variant=="head": raw["route_identity"]["head_at_issue"]="0"*40
                if variant!="canonical": raw["decision_sha256"]=sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-d0-phased-route/v1",raw,"decision_sha256")
                route.write_bytes(sd0._canon(raw))
            tcp=[]
            try:
                with self.client_context(), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                    try: result=sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:tcp.append(1) or True)
                    except sd0.SD0Error: result=None
                self.assertNotIsInstance(result,sd0.ReadyPreflight,variant); self.assertEqual([],tcp,variant); self.assertFalse(sd0._READY); self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists()); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
            finally:
                if restore is not None: route.chmod(restore)

    def assert_full_context_mutation_matrix(self) -> tuple[int,int]:
        ready=self.ready_preflight(); expected=copy.deepcopy(sd0._READY[ready.digest][1]); expected["authority_binding_results"]=[{"path":"authority-a","expected_sha256":"1"*64,"actual_sha256":"1"*64,"matched":True},{"path":"authority-b","expected_sha256":"2"*64,"actual_sha256":"2"*64,"matched":True}]; expected["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",expected,"context_sha256")
        with self.client_context(): self.assertTrue(sd0._context_is_ready(expected,expected))
        leaves=[]
        def walk(value,path):
            if isinstance(value,dict):
                for key,item in value.items():
                    if path==( ) and key=="context_sha256": continue
                    walk(item,path+(key,))
            elif isinstance(value,list):
                for index,item in enumerate(value): walk(item,path+(index,))
            else: leaves.append(path)
        def replace(value,path,new):
            target=value
            for part in path[:-1]: target=target[part]
            old=target[path[-1]]
            target[path[-1]]= (not old) if isinstance(old,bool) else (old+1 if isinstance(old,int) else (old+"x" if isinstance(old,str) else None))
        walk(expected,())
        for path in leaves:
            candidate=copy.deepcopy(expected); replace(candidate,path,None); candidate["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",candidate,"context_sha256")
            with self.client_context(): self.assertFalse(sd0._context_is_ready(candidate,expected),path)
        structural=0
        for key in ("authority_binding_results","static_path_results","network_output_absence"):
            for change in ("missing","extra","swap"):
                candidate=copy.deepcopy(expected); values=candidate[key]
                if not values: continue
                if change=="missing": values.pop()
                elif change=="extra": values.append(copy.deepcopy(values[0]))
                elif len(values)>1: values[0],values[1]=values[1],values[0]
                else: continue
                candidate["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",candidate,"context_sha256")
                with self.client_context(): self.assertFalse(sd0._context_is_ready(candidate,expected),(key,change))
                structural+=1
        malicious=copy.deepcopy(expected); malicious["authority_binding_results"][0]={"path":"evil","expected_sha256":"f"*64,"actual_sha256":"f"*64,"matched":True}; malicious["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",malicious,"context_sha256")
        with self.client_context(): self.assertFalse(sd0._context_is_ready(malicious,expected),"malicious authority")
        structural+=1
        for key in ("branch","route_binding"):
            candidate=copy.deepcopy(expected); candidate.pop(key); candidate["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",candidate,"context_sha256")
            with self.client_context(): self.assertFalse(sd0._context_is_ready(candidate,expected),(key,"missing"))
            structural+=1
        return len(leaves),structural

    def forged_ready_variants(self):
        ready=self.ready_preflight(); context=copy.deepcopy(sd0._READY[ready.digest][1]); base=ready.document
        for key in ("route_binding","authority_binding_results","static_path_results","output_path_results","request_plan_sha256"):
            doc=copy.deepcopy(base)
            if key=="route_binding": doc[key]["branch"]="forged"
            elif key=="authority_binding_results": doc[key].append({"path":"evil","expected_sha256":"0"*64,"actual_sha256":"0"*64,"matched":True})
            elif key=="static_path_results": doc[key][0]["present"]=False
            elif key=="output_path_results": doc[key].reverse()
            else: doc[key]="0"*64
            doc["preflight_sha256"]=sd0._self("pitar1/sd0-preflight/v1",doc,"preflight_sha256")
            forged=sd0.ReadyPreflight(sd0._canon(doc),doc["preflight_sha256"]); yield key,forged,context

    def assert_integrated_header_failure(self, partial: bool) -> None:
        ready=self.ready_preflight(); self.persist_ready(ready); closes=[]
        def headers():
            if partial: yield ("Content-Length","42")
            raise RuntimeError("headers")
        Resp=type("Resp",(),{"status":200,"getheaders":lambda _s:headers(),"close":lambda _s:closes.append("response")})
        Conn=type("Conn",(),{"__init__":lambda s,*a,**k:setattr(s,"sock",object()),"set_tunnel":lambda *_:None,"connect":lambda *_:None,"putrequest":lambda *a,**k:None,"putheader":lambda *a,**k:None,"endheaders":lambda *_:None,"getresponse":lambda _s:Resp(),"close":lambda _s:closes.append("connection")})
        Ctx=type("Ctx",(),{"wrap_socket":lambda _s,sock,**k:sock})
        with self.client_context(), patch.object(sd0.http.client,"HTTPConnection",Conn), patch.object(sd0.ssl,"create_default_context",return_value=Ctx()), self.assertRaises(sd0.SD0Error) as raised: sd0.execute(self.root,ready=ready)
        self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE",raised.exception.state); rows=(self.root/sd0.NETWORK_PATHS[0]).read_text().splitlines(); self.assertEqual(1,len(rows)); row=json.loads(rows[0]); self.assertEqual(200,row["status_code"]); self.assertEqual("VALIDATED",row["tls_validation_result"]); self.assertEqual(0,row["response_body_bytes"]); self.assertEqual("RuntimeError",row["error_class"]); self.assertEqual(sd0._sha(sd0._canon([["Content-Length","42"]]) if partial else sd0._canon([])),row["response_headers_sha256"]); self.assertFalse((self.root/sd0.NETWORK_PATHS[1]).read_bytes()); self.assertTrue((self.root/sd0.NETWORK_PATHS[6]).exists()); self.assertTrue((self.root/sd0.NETWORK_PATHS[7]).exists()); self.assertEqual(["response","connection"],closes)

    def good_opener(self) -> tuple[list[sd0.Spec], object]:
        checksum = hashlib.sha256(b"archive header only").hexdigest().encode("ascii")
        replies = {
            "SD0-001": http_response(declared_length=42),
            "SD0-002": http_response(body=b"README"),
            "SD0-003": http_response(declared_length=7),
            "SD0-004": http_response(body=b"LICENSE"),
            "SD0-005": http_response(declared_length=80),
            "SD0-006": http_response(body=checksum + b"  BTCUSDT-1m-2024-03.zip\n"),
            "SD0-007": http_response(content_type="application/zip", declared_length=100),
        }
        calls: list[sd0.Spec] = []

        def opener(spec: sd0.Spec) -> sd0.HttpResponse:
            calls.append(spec)
            return replies[spec.request_id]

        return calls, opener

    def test_checked_in_plan_loads_is_canonical_and_is_exact_seven_request_allowlist(self) -> None:
        safe = sd0.SafeRoot(REPOSITORY)
        try:
            contract, plan, specs = sd0._load(safe)
        finally:
            safe.close()
        self.assertEqual(sd0._strict_json(PLAN_PATH.read_bytes()), plan)
        self.assertEqual("pitar1-sd0-measurement-contract.v1", contract["schema_version"])
        self.assertEqual(7, len(specs))
        self.assertEqual([item[0] for item in sd0.EXACT], [item.request_id for item in specs])
        self.assertEqual("SD0-007", specs[-1].request_id)
        self.assertEqual("HEAD", specs[-1].method)
        self.assertFalse(any(item.method == "GET" and item.url.endswith(".zip") for item in specs))

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(sd0.SD0Error) as raised:
                sd0._strict_json(raw)
            self.assertEqual("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", raised.exception.state)

    def test_plan_rejects_digest_route_and_request_shape_drift(self) -> None:
        attacks = []
        digest = copy.deepcopy(self.plan)
        digest["plan_sha256"] = "0" * 64
        attacks.append(digest)
        route = copy.deepcopy(self.plan)
        route["route_binding"]["cwd"] = "/tmp/not-authorized"
        route["plan_sha256"] = sd0._self("pitar1/sd0-request-plan/v1", route, "plan_sha256")
        attacks.append(route)
        request = copy.deepcopy(self.plan)
        request["requests"][6]["method"] = "GET"
        request["plan_sha256"] = sd0._self("pitar1/sd0-request-plan/v1", request, "plan_sha256")
        attacks.append(request)
        for attack in attacks:
            with self.subTest(attack=attack["requests"][-1]["method"]):
                with self.assertRaises(sd0.SD0Error):
                    sd0._validate_plan(attack)

    def test_preflight_route_authority_static_output_disk_tests_and_proxy_all_fail_closed(self) -> None:
        self.materialize_static_inputs()
        self.materialize_empty_output_parents()
        authority_contract = copy.deepcopy(self.runtime_contract)
        authority_contract["authority_bindings"] = [{"path": "authority.txt", "physical_sha256": "f" * 64}]
        (self.root / "authority.txt").write_text("wrong", encoding="utf-8")
        cases = [
            ("route", self.runtime_contract, lambda: patch.object(sd0, "_git", return_value="wrong"), "HALT_ROUTE_DRIFT_NEW_SOL_REVIEW"),
            ("authority", authority_contract, lambda: patch.object(sd0, "_git", side_effect=lambda _r,*a:self.plan["route_binding"]["branch"] if a[0]=="branch" else self.plan["route_binding"]["head"]), "HALT_ROUTE_DRIFT_NEW_SOL_REVIEW"),
            ("tests", self.runtime_contract, lambda: patch.object(sd0, "_git", side_effect=lambda _r,*a:self.plan["route_binding"]["branch"] if a[0]=="branch" else self.plan["route_binding"]["head"]), "WAIT_DATA_NO_FALLBACK"),
            ("proxy", self.runtime_contract, lambda: patch.object(sd0, "_git", side_effect=lambda _r,*a:self.plan["route_binding"]["branch"] if a[0]=="branch" else self.plan["route_binding"]["head"]), "WAIT_DATA_NETWORK_TRANSPORT_NO_REQUESTS"),
        ]
        for name, contract, git_patch, expected in cases:
            with self.subTest(name=name), self.client_context(contract=contract), git_patch(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=2**63)):
                result = sd0.preflight(
                    self.root,
                    tests_evidence={} if name == "tests" else TEST_EVIDENCE,
                    tcp_probe=(lambda *_: False) if name == "proxy" else (lambda *_: self.fail("proxy must not run")),
                )
            self.assertIsInstance(result, dict)
            self.assertEqual(expected, result["terminal_disposition"])
            self.assertEqual(0, result["external_requests_sent"])
        # Missing static input, existing output, and low disk must also stop
        # before the TCP probe and must not write a preflight document.
        (self.root / sd0.STATIC_PATHS[0]).unlink()
        with self.client_context(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=2**63)):
            result = sd0.preflight(self.root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: self.fail("no probe"))
        self.assertEqual("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", result["terminal_disposition"])
        self.materialize_static_inputs()
        existing = self.root / sd0.NETWORK_PATHS[0]
        existing.write_bytes(b"existing")
        with self.client_context(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=2**63)):
            result = sd0.preflight(self.root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: self.fail("no probe"))
        self.assertEqual("FAIL_CLOSED_NO_OVERWRITE", result["terminal_disposition"])
        existing.unlink()
        with self.client_context(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=0)):
            result = sd0.preflight(self.root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: self.fail("no probe"))
        self.assertEqual("WAIT_DATA_NO_FALLBACK", result["terminal_disposition"])
        self.assertFalse((self.root / sd0.PREFLIGHT_PATH).exists())

    def test_preflight_ready_is_persisted_create_once(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        self.assertEqual(ready.digest, sd0._strict_json((self.root / sd0.PREFLIGHT_PATH).read_bytes())["preflight_sha256"])
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised:
            sd0.persist_ready(self.root, ready)
        self.assertEqual("WAIT_DATA_NO_FALLBACK", raised.exception.state)
        with self.client_context(), patch.object(sd0.shutil, "disk_usage", return_value=SimpleNamespace(free=2**63)):
            result = sd0.preflight(self.root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: True)
        self.assertEqual("FAIL_CLOSED_NO_OVERWRITE", result["terminal_disposition"])

    def test_execute_requires_issued_same_process_and_exact_persisted_ready_before_opener_or_runtime(self) -> None:
        self.materialize_static_inputs()
        self.materialize_empty_output_parents()
        calls: list[sd0.Spec] = []
        opener = lambda spec: calls.append(spec)  # type: ignore[return-value]
        forged = sd0.ReadyPreflight({"terminal_disposition": "READY", "external_requests_sent": 0}, "b" * 64)
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised:
            sd0.execute(self.root, ready=forged, opener=opener)
        self.assertEqual("WAIT_DATA_NO_FALLBACK", raised.exception.state)
        self.assertEqual([], calls)
        self.assertFalse(any((self.root / rel).exists() for rel in sd0.NETWORK_PATHS))
        ready = self.ready_preflight()
        with self.client_context(), self.assertRaises(sd0.SD0Error):
            sd0.execute(self.root, ready=ready, opener=opener)
        self.assertEqual([], calls)
        ready = self.ready_preflight()  # Ordered lifecycle: the failed execute consumed the prior session.
        self.persist_ready(ready)
        persisted = json.loads((self.root / sd0.PREFLIGHT_PATH).read_text("utf-8"))
        persisted["request_plan_sha256"] = "0" * 64
        (self.root / sd0.PREFLIGHT_PATH).write_text(json.dumps(persisted), encoding="utf-8")
        with self.client_context(), self.assertRaises(sd0.SD0Error):
            sd0.execute(self.root, ready=ready, opener=opener)
        self.assertEqual([], calls)
        self.assertFalse((self.root / sd0.NETWORK_PATHS[0]).exists())

    def test_direct_bypass_is_zero_calls_and_zero_files(self) -> None:
        self.materialize_static_inputs()
        self.materialize_empty_output_parents()
        calls: list[sd0.Spec] = []
        with self.client_context(), self.assertRaises(sd0.SD0Error):
            sd0.execute(self.root, opener=lambda spec: calls.append(spec))
        self.assertEqual([], calls)
        self.assertFalse(any((self.root / rel).exists() for rel in sd0.NETWORK_PATHS + (sd0.PREFLIGHT_PATH,)))

    def test_safe_root_rejects_final_and_parent_symlinks_and_uses_atomic_no_follow_create(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "final").symlink_to(outside / "stolen")
        safe = sd0.SafeRoot(self.root)
        try:
            with self.assertRaises(sd0.SD0Error) as raised:
                safe.create("final", b"x")
            self.assertEqual("FAIL_CLOSED_NO_OVERWRITE", raised.exception.state)
        finally:
            safe.close()
        (self.root / "parent").symlink_to(outside, target_is_directory=True)
        safe = sd0.SafeRoot(self.root)
        try:
            with self.assertRaises(sd0.SD0Error) as raised:
                safe.create("parent/child", b"x")
            self.assertEqual("FAIL_CLOSED_NO_OVERWRITE", raised.exception.state)
        finally:
            safe.close()
        self.assertFalse((outside / "child").exists())
        calls: list[tuple[object, int]] = []
        real_open = os.open

        def audited_open(path, flags, *args, **kwargs):
            if path == "atomic":
                calls.append((path, flags))
            return real_open(path, flags, *args, **kwargs)

        safe = sd0.SafeRoot(self.root)
        try:
            with patch.object(sd0.os, "open", side_effect=audited_open):
                fd = safe.create("atomic", b"sealed")
            os.close(fd)
        finally:
            safe.close()
        self.assertEqual(1, len(calls))
        self.assertTrue(calls[0][1] & os.O_EXCL)
        self.assertTrue(calls[0][1] & os.O_NOFOLLOW)

    def test_safe_root_treats_a_missing_intermediate_parent_as_an_absent_output(self) -> None:
        safe = sd0.SafeRoot(self.root)
        try:
            self.assertFalse(safe.exists_or_link("not-created-yet/nested/output.json"))
        finally:
            safe.close()

    def test_observe_rejects_redirect_status_content_type_headers_bodies_and_total_caps(self) -> None:
        spec = self.specs[1]
        attacks = [
            (http_response(status=302, headers=(("Location", "https://elsewhere/"),)), "HALT_PROTOCOL_VIOLATION"),
            (http_response(content_type="text/html"), "WAIT_DATA_SOURCE_CONTRACT_MISMATCH"),
            (http_response(headers=(("Cookie", "x=y"),)), "HALT_PROTOCOL_VIOLATION"),
            (http_response(body=b"x" * (spec.cap + 1)), "HALT_RESOURCE_CAP"),
            (http_response(body=b"x", declared_length=2), "WAIT_DATA_SOURCE_CONTRACT_MISMATCH"),
        ]
        for reply, expected in attacks:
            with self.subTest(expected=expected), self.assertRaises(sd0.SD0Error) as raised:
                sd0._observe(spec, reply, 0, "2026-01-01T00:00:00Z", 0)
            self.assertEqual(expected, raised.exception.state)
        with self.assertRaises(sd0.SD0Error) as raised:
            sd0._observe(spec, http_response(body=b"x"), 2162688, "2026-01-01T00:00:00Z", 0)
        self.assertEqual("HALT_RESOURCE_CAP", raised.exception.state)
        with self.assertRaises(sd0.SD0Error) as raised:
            sd0._observe(self.specs[0], http_response(body=b"x", declared_length=1), 0, "2026-01-01T00:00:00Z", 0)
        self.assertEqual("HALT_NO_ROW_LEAK_VIOLATION", raised.exception.state)

    def test_stdlib_proxy_opener_reads_no_more_than_declared_cap_not_cap_plus_one(self) -> None:
        class FakeResponse:
            status = 200
            def getheaders(self): return [("Content-Length", "1048576"), ("Content-Type", "text/plain")]
            def read(self, count):
                self.count = count
                return b"x" * count
        class FakeConnection:
            instance = None
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
                self.sock = object()
                FakeConnection.instance = self
            def set_tunnel(self, host, port): self.tunnel = (host, port)
            def connect(self): pass
            def putrequest(self, *args, **kwargs): pass
            def putheader(self, *args): pass
            def endheaders(self): pass
            def getresponse(self): self.response = FakeResponse(); return self.response
            def close(self): pass
        class FakeContext:
            def wrap_socket(self, sock, server_hostname): return sock
        with patch.object(sd0.http.client, "HTTPConnection", FakeConnection), patch.object(sd0.ssl, "create_default_context", return_value=FakeContext()):
            reply = sd0.StdlibProxyOpener()(self.specs[1])
        self.assertEqual(sd0.PROXY, f"http://{FakeConnection.instance.host}:{FakeConnection.instance.port}")
        self.assertEqual(self.specs[1].cap, FakeConnection.instance.response.count)
        self.assertEqual(self.specs[1].cap, len(reply.body))

    def test_successful_run_requires_exact_seven_no_zip_get_and_closed_output_schemas(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        calls, opener = self.good_opener()
        with self.client_context():
            closure = sd0.execute(self.root, ready=ready, opener=opener)  # Expected to expose any sealing defect.
        self.assertEqual("WAIT_DATA_TERMS_D0_DENIED", closure["terminal_disposition"])
        self.assertEqual([item.request_id for item in self.specs], [item.request_id for item in calls])
        self.assertFalse(any(item.method == "GET" and item.url.endswith(".zip") for item in calls))
        request_records = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[0]).read_text("utf-8").splitlines()]
        header_records = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[1]).read_text("utf-8").splitlines()]
        self.assertEqual(7, len(request_records))
        self.assertEqual(7, len(header_records))
        for role, records in (("WRITE_ONCE_LOGICAL_REQUEST_LEDGER", request_records), ("WRITE_ONCE_RESPONSE_METADATA_LEDGER", header_records)):
            exact = set(self.runtime_contract["artifact_schemas"][role]["exact_record_fields"])
            self.assertTrue(all(set(record) == exact for record in records))
        head = sd0._strict_json((self.root / sd0.NETWORK_PATHS[5]).read_bytes())
        self.assertEqual(set(self.runtime_contract["artifact_schemas"]["ARCHIVE_HEADER_METADATA_ONLY"]["exact_fields"]), set(head))
        self.assertEqual(100, head["declared_content_length"])
        self.assertEqual(header_records[-1]["headers_sha256"], head["headers_sha256"])
        self.assertEqual("WAIT_DATA_TERMS_D0_DENIED", closure["terms_disposition"])
        self.assertEqual(hashlib.sha256((self.root / sd0.NETWORK_PATHS[2]).read_bytes()).hexdigest(), closure["document_identities"][0]["physical_sha256"])
        self.assertIsNotNone(closure["checksum_result"])
        self.assertIsNotNone(closure["zip_head_result"])
        for role, path in (
            ("FAIL_CLOSED_SD0_RESULT", sd0.NETWORK_PATHS[6]),
            ("CONTENT_IDENTITY_INVENTORY", sd0.NETWORK_PATHS[7]),
        ):
            value = sd0._strict_json((self.root / path).read_bytes())
            self.assertEqual(set(self.runtime_contract["artifact_schemas"][role]["exact_fields"]), set(value))

    def test_first_network_failure_stops_preserves_accounting_closure_inventory_and_cannot_retry(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        calls, good = self.good_opener()
        def failing(spec: sd0.Spec) -> sd0.HttpResponse:
            if spec.request_id == "SD0-003":
                calls.append(spec)
                return http_response(status=500)
            return good(spec)
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised:
            sd0.execute(self.root, ready=ready, opener=failing)
        self.assertEqual("HALT_PROTOCOL_VIOLATION", raised.exception.state)
        self.assertEqual(["SD0-001", "SD0-002", "SD0-003"], [item.request_id for item in calls])
        self.assertTrue((self.root / sd0.NETWORK_PATHS[0]).exists())
        self.assertTrue((self.root / sd0.NETWORK_PATHS[1]).exists())
        self.assertTrue((self.root / sd0.NETWORK_PATHS[6]).exists())
        self.assertTrue((self.root / sd0.NETWORK_PATHS[7]).exists())
        with self.client_context(), self.assertRaises(sd0.SD0Error) as retry:
            sd0.execute(self.root, ready=ready, opener=good)
        self.assertEqual("WAIT_DATA_NO_FALLBACK", retry.exception.state)

    def test_partial_failure_preserves_the_actual_failed_response_headers_and_status(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        calls, good = self.good_opener()

        def failing(spec: sd0.Spec) -> sd0.HttpResponse:
            return http_response(status=500, body=b"failure", declared_length=7) if spec.request_id == "SD0-003" else good(spec)

        with self.client_context():
            with self.assertRaises(sd0.SD0Error):
                sd0.execute(self.root, ready=ready, opener=failing)
        requests = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[0]).read_text("utf-8").splitlines()]
        headers = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[1]).read_text("utf-8").splitlines()]
        self.assertEqual(3, len(requests))
        self.assertEqual(3, len(headers))
        self.assertEqual(500, requests[-1]["status_code"])
        self.assertEqual(500, headers[-1]["status_code"])
        self.assertEqual("HALT_NO_ROW_LEAK_VIOLATION", requests[-1]["terminal_disposition"])
        self.assertEqual("HALT_NO_ROW_LEAK_VIOLATION", headers[-1]["terminal_disposition"])

    def test_ready_document_mutation_or_self_hash_drift_rejects_before_any_opener_call(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        # ReadyPreflight is frozen only shallowly; a valid implementation must
        # recanonicalize its persisted document before it authorizes I/O.
        ready.document["created_at_utc"] = "tampered-after-issue"
        (self.root / sd0.PREFLIGHT_PATH).write_text(json.dumps(ready.document), encoding="utf-8")
        calls: list[sd0.Spec] = []
        _, valid = self.good_opener()
        def opener(spec: sd0.Spec) -> sd0.HttpResponse:
            calls.append(spec)
            return valid(spec)
        with self.client_context():
            with self.assertRaises(sd0.SD0Error) as raised:
                sd0.execute(self.root, ready=ready, opener=opener)
        self.assertEqual("WAIT_DATA_NO_FALLBACK", raised.exception.state)
        self.assertEqual([], calls)

    def test_inventory_covers_every_created_allowlisted_output_except_its_own_self_hash(self) -> None:
        ready = self.ready_preflight()
        self.persist_ready(ready)
        _, opener = self.good_opener()
        with self.client_context():
            sd0.execute(self.root, ready=ready, opener=opener)
        inventory = sd0._strict_json((self.root / sd0.NETWORK_PATHS[7]).read_bytes())
        listed = {item["path"] for item in inventory["artifact_identities"]}
        self.assertEqual(set(sd0.NETWORK_PATHS[:-1]), listed)

    def test_local_artifact_cap_is_enforced_not_merely_declared_in_the_plan(self) -> None:
        # A lowered cap makes this deterministic offline test practical.  The
        # real plan's 10 MiB cap is otherwise larger than its seven body caps.
        limited_plan = copy.deepcopy(self.plan)
        limited_plan["resource_caps"]["maximum_total_local_artifact_bytes"] = 1
        ready = self.ready_preflight()
        self.persist_ready(ready)
        _, opener = self.good_opener()
        with self.client_context(), patch.object(sd0, "_load", return_value=(self.runtime_contract, limited_plan, self.specs)):
            with self.assertRaises(sd0.SD0Error) as raised:
                sd0.execute(self.root, ready=ready, opener=opener)
        self.assertEqual("HALT_RESOURCE_CAP", raised.exception.state)

    # R3-T01: a received response without Content-Length is never rewritten as no response.
    def test_r3_t01_missing_content_length_seals_actual_status_and_headers(self) -> None:
        class Response:
            status=200
            def getheaders(self): return [("Content-Type","text/plain"),("X-Proof","seen")]
            def read(self, _count): raise AssertionError("missing CL must not read")
        class Connection:
            def __init__(self,*args,**kwargs): self.sock=object()
            def set_tunnel(self,*args): pass
            def connect(self): pass
            def putrequest(self,*args,**kwargs): pass
            def putheader(self,*args): pass
            def endheaders(self): pass
            def getresponse(self): return Response()
            def close(self): pass
        class Context:
            def wrap_socket(self,sock,**kwargs): return sock
        with patch.object(sd0.http.client,"HTTPConnection",Connection), patch.object(sd0.ssl,"create_default_context",return_value=Context()):
            observed=sd0.StdlibProxyOpener()(self.specs[2])
        ready = self.ready_preflight(); self.persist_ready(ready)
        calls, good = self.good_opener()
        def missing(spec: sd0.Spec) -> sd0.HttpResponse:
            if spec.request_id == "SD0-003":
                calls.append(spec)
                return observed
            return good(spec)
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised:
            sd0.execute(self.root, ready=ready, opener=missing)
        self.assertEqual("WAIT_DATA_SOURCE_CONTRACT_MISMATCH", raised.exception.state)
        requests = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[0]).read_text().splitlines()]
        headers = [json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[1]).read_text().splitlines()]
        self.assertEqual(200, requests[-1]["status_code"]); self.assertEqual(200, headers[-1]["status_code"])
        self.assertTrue((self.root / sd0.NETWORK_PATHS[6]).exists()); self.assertTrue((self.root / sd0.NETWORK_PATHS[7]).exists())

    # R3-T02: headers proving a cap violation are sufficient; GET body is not read.
    def test_r3_t02_declared_over_cap_is_accounted_without_body_read(self) -> None:
        class FakeResponse:
            status = 200
            def getheaders(self): return [("Content-Length", "1048577"), ("Content-Type", "text/plain")]
            def read(self, _count): self.fail_called = True; raise AssertionError("must not read")
        class FakeConnection:
            def __init__(self, *args, **kwargs): self.sock = object()
            def set_tunnel(self, *args): pass
            def connect(self): pass
            def putrequest(self, *args, **kwargs): pass
            def putheader(self, *args): pass
            def endheaders(self): pass
            def getresponse(self): self.response = FakeResponse(); return self.response
            def close(self): pass
        class Context:
            def wrap_socket(self, sock, **kwargs): return sock
        with patch.object(sd0.http.client, "HTTPConnection", FakeConnection), patch.object(sd0.ssl, "create_default_context", return_value=Context()):
            reply = sd0.StdlibProxyOpener()(self.specs[1])
        self.assertEqual(b"", reply.body)
        record, header, state = sd0._make_observation(self.specs[1], reply, 0, "2026-01-01T00:00:00Z", 0)
        self.assertEqual(200, record["status_code"]); self.assertIsNotNone(header); self.assertEqual("HALT_RESOURCE_CAP", state)

    def test_r3_header_proven_rejections_never_call_get_read(self) -> None:
        cases = [
            [("Content-Length","5"),("Content-Type","text/plain")],
            [("Content-Length","5"),("Content-Type","text/plain"),("Location","https://elsewhere/")],
            [("Content-Length","5"),("Content-Type","text/html")],
            [("Content-Length","5"),("Content-Type","text/plain"),("Cookie","secret")],
            [("Content-Length","5"),("Content-Type","text/plain"),("X-Long","x"*65537)],
        ]
        for index, headers in enumerate(cases):
            class Response:
                status = 500 if index == 0 else 200
                def getheaders(self): return headers
                def read(self, _count): raise AssertionError("header-proven rejection read body")
            class Connection:
                def __init__(self,*args,**kwargs): self.sock=object()
                def set_tunnel(self,*args): pass
                def connect(self): pass
                def putrequest(self,*args,**kwargs): pass
                def putheader(self,*args): pass
                def endheaders(self): pass
                def getresponse(self): return Response()
                def close(self): pass
            class Context:
                def wrap_socket(self,sock,**kwargs): return sock
            with self.subTest(case=index), patch.object(sd0.http.client,"HTTPConnection",Connection), patch.object(sd0.ssl,"create_default_context",return_value=Context()):
                reply=sd0.StdlibProxyOpener()(self.specs[1])
            self.assertEqual(b"",reply.body)

    # R3-T03: partial application bytes from IncompleteRead remain in evidence.
    def test_r3_t03_incomplete_read_partial_bytes_stop_without_later_request(self) -> None:
        class Response:
            status=200
            def getheaders(self): return [("Content-Type","text/plain"),("Content-Length","10")]
            def read(self, _count): raise http.client.IncompleteRead(b"part",6)
        class Connection:
            def __init__(self,*args,**kwargs): self.sock=object()
            def set_tunnel(self,*args): pass
            def connect(self): pass
            def putrequest(self,*args,**kwargs): pass
            def putheader(self,*args): pass
            def endheaders(self): pass
            def getresponse(self): return Response()
            def close(self): pass
        class Context:
            def wrap_socket(self,sock,**kwargs): return sock
        with patch.object(sd0.http.client,"HTTPConnection",Connection), patch.object(sd0.ssl,"create_default_context",return_value=Context()):
            partial=sd0.StdlibProxyOpener()(self.specs[1])
        ready = self.ready_preflight(); self.persist_ready(ready); calls, good = self.good_opener()
        def incomplete(spec: sd0.Spec) -> sd0.HttpResponse:
            if spec.request_id == "SD0-002":
                calls.append(spec); return partial
            return good(spec)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root, ready=ready, opener=incomplete)
        records=[json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[0]).read_text().splitlines()]
        self.assertEqual(["SD0-001","SD0-002"],[row["request_id"] for row in records]); self.assertEqual(4,records[-1]["response_body_bytes"])

    # R3-T04: all pre-response transport failures become one null-status attempt.
    def test_r3_t04_pre_response_transport_failures_are_total(self) -> None:
        for exc in (socket.timeout(), TimeoutError(), ConnectionError(), ssl.SSLError("bad"), OSError("bad"), http.client.HTTPException("bad")):
            with self.subTest(exc=type(exc).__name__):
                self.tearDown(); self.setUp(); ready=self.ready_preflight(); self.persist_ready(ready); calls=[]
                def broken(spec, failure=exc): calls.append(spec); raise failure
                with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root, ready=ready, opener=broken)
                rows=[json.loads(line) for line in (self.root / sd0.NETWORK_PATHS[0]).read_text().splitlines()]
                self.assertEqual(1,len(rows)); self.assertIsNone(rows[0]["status_code"]); self.assertFalse((self.root / sd0.NETWORK_PATHS[1]).read_bytes()); self.assertEqual(1,len(calls))

    def test_r3_read_transport_failure_after_headers_keeps_actual_metadata(self) -> None:
        for exc in (socket.timeout(), OSError("read failed"), http.client.HTTPException("read failed")):
            class Response:
                status=200
                def getheaders(self): return [("Content-Type","text/plain"),("Content-Length","5")]
                def read(self, _count, failure=exc): raise failure
            class Connection:
                def __init__(self,*args,**kwargs): self.sock=object()
                def set_tunnel(self,*args): pass
                def connect(self): pass
                def putrequest(self,*args,**kwargs): pass
                def putheader(self,*args): pass
                def endheaders(self): pass
                def getresponse(self): return Response()
                def close(self): pass
            class Context:
                def wrap_socket(self,sock,**kwargs): return sock
            with self.subTest(exc=type(exc).__name__), patch.object(sd0.http.client,"HTTPConnection",Connection), patch.object(sd0.ssl,"create_default_context",return_value=Context()):
                reply=sd0.StdlibProxyOpener()(self.specs[1])
            record,header,state=sd0._make_observation(self.specs[1],reply,0,"2026-01-01T00:00:00Z",0)
            self.assertEqual(200,record["status_code"]); self.assertIsNotNone(header); self.assertEqual("WAIT_DATA_NO_FALLBACK",state)

    # R3-T05/T06: a token and copied preflight cannot cross the issuing root boundary.
    def test_r3_t05_t06_cross_root_ready_is_rejected_before_write_or_opener(self) -> None:
        ready=self.ready_preflight(); self.persist_ready(ready)
        with tempfile.TemporaryDirectory() as other_raw:
            other=Path(other_raw)
            for rel in sd0.STATIC_PATHS:
                target=other/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((self.root/rel).read_bytes())
            for rel in sd0.NETWORK_PATHS+(sd0.PREFLIGHT_PATH,): (other/rel).parent.mkdir(parents=True,exist_ok=True)
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(other,ready)
            (other/sd0.PREFLIGHT_PATH).write_bytes((self.root/sd0.PREFLIGHT_PATH).read_bytes())
            calls=[]
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(other,ready=ready,opener=lambda spec: calls.append(spec))
            self.assertEqual([],calls); self.assertFalse(any((other/path).exists() for path in sd0.NETWORK_PATHS))

    # R3-T07 strengthens the R2 cap case with the explicit no-call/no-output proof.
    def test_r3_t07_initial_cap_guard_has_zero_calls_and_zero_runtime_outputs(self) -> None:
        limited=copy.deepcopy(self.plan); limited["resource_caps"]["maximum_total_local_artifact_bytes"]=1
        ready=self.ready_preflight(); self.persist_ready(ready); calls=[]
        with self.client_context(), patch.object(sd0,"_load",return_value=(self.runtime_contract,limited,self.specs)), self.assertRaises(sd0.SD0Error) as raised:
            sd0.execute(self.root,ready=ready,opener=lambda spec: calls.append(spec))
        self.assertEqual("HALT_RESOURCE_CAP",raised.exception.state); self.assertEqual([],calls); self.assertFalse(any((self.root/path).exists() for path in sd0.NETWORK_PATHS))

    # R3-T06 independently proves copied persisted evidence cannot authorize execution in another root.
    def test_r3_t06_copied_persisted_ready_rejects_execute_before_opener(self) -> None:
        ready=self.ready_preflight(); self.persist_ready(ready)
        with tempfile.TemporaryDirectory() as other_raw:
            other=Path(other_raw)
            for rel in sd0.STATIC_PATHS:
                target=other/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((self.root/rel).read_bytes())
            for rel in sd0.NETWORK_PATHS+(sd0.PREFLIGHT_PATH,): (other/rel).parent.mkdir(parents=True,exist_ok=True)
            (other/sd0.PREFLIGHT_PATH).write_bytes((self.root/sd0.PREFLIGHT_PATH).read_bytes())
            calls=[]
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(other,ready=ready,opener=lambda spec: calls.append(spec))
            self.assertEqual([],calls); self.assertFalse(any((other/path).exists() for path in sd0.NETWORK_PATHS))

    # R3-T08: the stdlib HEAD branch is header-only and never invokes read.
    def test_r3_t08_stdlib_head_never_calls_read(self) -> None:
        class FakeResponse:
            status=200
            def getheaders(self): return [("Content-Length","42"),("Content-Type","text/plain")]
            def read(self, _count): raise AssertionError("HEAD read forbidden")
        class FakeConnection:
            def __init__(self,*args,**kwargs): self.sock=object()
            def set_tunnel(self,*args): pass
            def connect(self): pass
            def putrequest(self,*args,**kwargs): pass
            def putheader(self,*args): pass
            def endheaders(self): pass
            def getresponse(self): return FakeResponse()
            def close(self): pass
        class Context:
            def wrap_socket(self,sock,**kwargs): return sock
        with patch.object(sd0.http.client,"HTTPConnection",FakeConnection), patch.object(sd0.ssl,"create_default_context",return_value=Context()): reply=sd0.StdlibProxyOpener()(self.specs[0])
        self.assertEqual(b"",reply.body)

    # R3-T09: an injected HEAD body is accounted before the hard no-row stop.
    def test_r3_t09_custom_head_body_is_accounted_as_no_row_leak(self) -> None:
        ready=self.ready_preflight(); self.persist_ready(ready)
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised:
            sd0.execute(self.root,ready=ready,opener=lambda _spec: http_response(body=b"x",declared_length=1))
        self.assertEqual("HALT_NO_ROW_LEAK_VIOLATION",raised.exception.state)
        row=json.loads((self.root/sd0.NETWORK_PATHS[0]).read_text().splitlines()[0]); self.assertEqual(1,row["response_body_bytes"]); self.assertEqual("HALT_NO_ROW_LEAK_VIOLATION",row["terminal_disposition"])

    # R3-T10: exact production gate blocks all entrypoints before input/socket/output work.
    def test_r3_t10_unpatched_production_suspension_gate_blocks_every_entrypoint(self) -> None:
        workspace_paths=sd0.NETWORK_PATHS+(sd0.PREFLIGHT_PATH,)
        before=workspace_output_snapshot(workspace_paths)
        calls=[]
        with self.assertRaises(sd0.SD0Error): sd0.preflight(REPOSITORY,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_: calls.append("tcp"))
        with self.assertRaises(sd0.SD0Error): sd0.main(["--tests-evidence","does-not-exist.json"])
        forged=sd0.ReadyPreflight(b"{}","0"*64)
        with self.assertRaises(sd0.SD0Error): sd0.persist_ready(REPOSITORY,forged)
        with self.assertRaises(sd0.SD0Error): sd0.execute(REPOSITORY,ready=forged,opener=lambda _spec: calls.append("opener"))
        self.assertEqual([],calls); self.assertEqual(before,workspace_output_snapshot(workspace_paths))

    def test_r4_t11_context_static_change_prevents_ready_issue(self) -> None:
        ready=self.ready_preflight(); self.assertIsInstance(ready,sd0.ReadyPreflight)
        # A post-issuance static mutation is rejected by persistence before output.
        (self.root/sd0.STATIC_PATHS[0]).write_bytes(b"changed")
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
        self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())

    def test_r4_t12_context_git_change_prevents_ready_issue(self) -> None:
        ready=self.ready_preflight()
        with self.client_context(), patch.object(sd0,"_git",return_value="changed"), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
        self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())

    def test_r4_t13_context_projection_and_identity_readiness(self) -> None:
        ready=self.ready_preflight(); snapshot,context=sd0._READY[ready.digest]
        self.assertEqual(ready.document["authority_binding_results"],context["authority_binding_results"])
        self.assertEqual(ready.document["static_path_results"],context["static_path_results"])
        with self.client_context(): self.assertTrue(sd0._context_is_ready(context,context))
        mutations=(
            ("root_device",context["root_device"]+1),("root_inode",context["root_inode"]+1),
            ("branch","other"),("head","0"*40),("route_binding",{}),
            ("contract_physical_sha256","0"*64),("contract_canonical_sha256","0"*64),
            ("plan_physical_sha256","0"*64),("plan_canonical_sha256","0"*64),
            ("authority_binding_results",[{"matched":False,"expected_sha256":"0"*64,"actual_sha256":"0"*64}]),
            ("static_path_results",[]),("network_output_absence",[]),
        )
        for key,value in mutations:
            changed=copy.deepcopy(context); changed[key]=value
            with self.client_context(): self.assertFalse(sd0._context_is_ready(changed,context),key)

    def test_r4_t14_exact_cap_has_zero_calls_zero_outputs(self) -> None:
        limited=copy.deepcopy(self.plan); ready=self.ready_preflight(); self.persist_ready(ready)
        limited["resource_caps"]["maximum_total_local_artifact_bytes"]=(self.root/sd0.PREFLIGHT_PATH).stat().st_size; calls=[]
        with self.client_context(), patch.object(sd0,"_load",return_value=(self.runtime_contract,limited,self.specs)), self.assertRaises(sd0.SD0Error) as raised: sd0.execute(self.root,ready=ready,opener=lambda spec:calls.append(spec))
        self.assertEqual("HALT_RESOURCE_CAP",raised.exception.state); self.assertEqual([],calls); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))

    def test_r4_t15_duplicate_content_length_rejected(self) -> None:
        for values in (("5","5"),("5","999999")):
            reply=sd0.HttpResponse(200,(("Content-Type","text/plain"),("Content-Length",values[0]),("Content-Length",values[1])),b"")
            _,_,state=sd0._make_observation(self.specs[1],reply,0,"2026-01-01T00:00:00Z",0); self.assertEqual("HALT_PROTOCOL_VIOLATION",state)

    def test_r4_t16_critical_header_cardinality_and_secrets(self) -> None:
        for header in (("Content-Type","text/plain"),("Location",""),("Transfer-Encoding","chunked"),("Content-Encoding","gzip"),("Cookie","secret")):
            base=[("Content-Length","5"),("Content-Type","text/plain")]; base.append(header)
            _,h,state=sd0._make_observation(self.specs[1],sd0.HttpResponse(200,tuple(base),b""),0,"2026-01-01T00:00:00Z",0); self.assertEqual("HALT_PROTOCOL_VIOLATION",state)
            if header[0]=="Cookie": self.assertIsNone(h)

    def test_r4_t17_content_length_grammar_is_total(self) -> None:
        for value in ("", "01", "+1", " 1", "1,2", "9"*10, "\u0661"):
            reply=sd0.HttpResponse(200,(("Content-Length",value),("Content-Type","text/plain")),b"")
            _,_,state=sd0._make_observation(self.specs[1],reply,0,"2026-01-01T00:00:00Z",0); self.assertEqual("WAIT_DATA_SOURCE_CONTRACT_MISMATCH",state)

    def test_r4_t18_lossy_or_control_headers_fail_closed(self) -> None:
        for name,value in (("X-\u4e2d","x"),("X-Test","\u20ac"),("X-Test","a\nb"),("X-Test","a\x00b")):
            normal=sd0._normalize_headers((("Content-Length","5"),("Content-Type","text/plain"),(name,value)))
            self.assertIsNotNone(normal.state)

    def test_r4_t19_shared_normalizer_has_single_ordered_evidence(self) -> None:
        headers=(("X-B","2"),("Content-Length","5"),("Content-Type","text/plain"),("X-A","1"))
        one=sd0._normalize_headers(headers); two=sd0._normalize_headers(headers)
        self.assertEqual(one.evidence,two.evidence); self.assertEqual(one.pairs,headers); self.assertEqual(one.evidence,sd0._canon([[k,v] for k,v in headers]))
        class Response:
            status=200
            def getheaders(self): return list(headers)
            def read(self,_count): return b"hello"
            def close(self): pass
        class Connection:
            def __init__(self,*args,**kwargs): self.sock=object()
            def set_tunnel(self,*args): pass
            def connect(self): pass
            def putrequest(self,*args,**kwargs): pass
            def putheader(self,*args): pass
            def endheaders(self): pass
            def getresponse(self): return Response()
            def close(self): pass
        class Context:
            def wrap_socket(self,sock,**kwargs): return sock
        with patch.object(sd0.http.client,"HTTPConnection",Connection), patch.object(sd0.ssl,"create_default_context",return_value=Context()): reply=sd0.StdlibProxyOpener()(self.specs[1])
        _,header,state=sd0._make_observation(self.specs[1],reply,0,"2026-01-01T00:00:00Z",0)
        self.assertIsNone(state); self.assertEqual(headers,reply.headers); self.assertEqual(len(one.evidence),header["header_bytes"]); self.assertEqual(sd0._sha(one.evidence),header["headers_sha256"])

    def test_r4_t20_unexpected_header_object_is_totalized(self) -> None:
        reply=sd0.HttpResponse(200,(("Content-Length","5"),("Content-Type","text/plain"),(1,"x")),b"")
        record,header,state=sd0._make_observation(self.specs[1],reply,0,"2026-01-01T00:00:00Z",0)
        self.assertEqual(200,record["status_code"]); self.assertIsNone(header); self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE",state)
        class RaisingHeaders:
            def __iter__(self): raise RuntimeError("parser failure")
        self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE",sd0._normalize_headers(RaisingHeaders()).state)
        ready=self.ready_preflight(); self.persist_ready(ready); calls=[]
        def bad_opener(spec): calls.append(spec.request_id); raise RuntimeError("opener failure")
        with self.client_context(), self.assertRaises(sd0.SD0Error) as raised: sd0.execute(self.root,ready=ready,opener=bad_opener)
        self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE",raised.exception.state); self.assertEqual(["SD0-001"],calls)
        row=json.loads((self.root/sd0.NETWORK_PATHS[0]).read_text().splitlines()[0]); self.assertIsNone(row["status_code"]); self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE",row["terminal_disposition"])

    def test_r5_t21_stable_unauthorized_final_git_never_issues_ready(self) -> None:
        self.materialize_static_inputs(); self.materialize_empty_output_parents()
        calls=[]
        def git(_root,*args):
            calls.append(args[0]); return self.plan["route_binding"]["branch"] if len(calls)<=1 else (self.plan["route_binding"]["head"] if len(calls)<=2 else "unauthorized")
        tcp=[]
        with self.client_context(), patch.object(sd0,"_git",side_effect=git), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)), self.assertRaises(sd0.SD0Error):
            sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:tcp.append(1) or True)
        self.assertFalse(sd0._READY); self.assertEqual([],tcp); self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())

    def test_r5_t22_root_identity_rehash_does_not_authorize(self) -> None:
        leaves,structural=self.assert_full_context_mutation_matrix(); self.assertGreater(leaves,20); self.assertGreater(structural,5)

    def test_r5_t23_actual_route_must_exist_and_be_regular(self) -> None:
        self.assert_route_failure_matrix()

    def test_r5_t24_actual_route_digest_cannot_be_declared_only(self) -> None:
        self.assert_route_failure_matrix()

    def test_r5_t25_rehashed_context_values_remain_externally_invalid(self) -> None:
        ready=self.ready_preflight(); context=sd0._READY[ready.digest][1]
        authority=copy.deepcopy(context["authority_binding_results"])+[{"path":"evil","expected_sha256":"0"*64,"actual_sha256":"0"*64,"matched":True}]
        static=copy.deepcopy(context["static_path_results"]); static[0]["physical_sha256"]="0"*64
        for key,value in (("resolved_root","/nope"),("branch","x"),("head","0"*40),("route_binding",{}),("route_physical_sha256","0"*64),("route_canonical_sha256","0"*64),("contract_physical_sha256","0"*64),("contract_canonical_sha256","0"*64),("plan_physical_sha256","0"*64),("plan_canonical_sha256","0"*64),("authority_binding_results",authority),("static_path_results",static),("network_output_absence",[])):
            changed=copy.deepcopy(context); changed[key]=value; changed["context_sha256"]=sd0._self("pitar1/sd0-ready-context/v1",changed,"context_sha256")
            with self.client_context(): self.assertFalse(sd0._context_is_ready(changed,context),key)

    def test_r5_t26_ready_document_projects_accepted_external_context(self) -> None:
        ready=self.ready_preflight(); context=sd0._READY[ready.digest][1]; self.assertTrue(sd0._projection_matches(ready.document,context))
        for key,forged,_context in self.forged_ready_variants(): self.assertFalse(sd0._projection_matches(forged.document,context),key)

    def test_r5_t27_post_issue_route_drift_rejects_persist_and_execute(self) -> None:
        for rel in (self.plan["route_binding"]["decision_path"],sd0.STATIC_PATHS[1],sd0.STATIC_PATHS[2],sd0.STATIC_PATHS[0]):
            self.tearDown(); self.setUp(); ready=self.ready_preflight(); (self.root/rel).write_bytes(b"drift")
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
            self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists(),rel)
        self.tearDown(); self.setUp(); ready=self.ready_preflight(); self.persist_ready(ready); (self.root/sd0.STATIC_PATHS[0]).write_bytes(b"drift"); calls=[]
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
        self.assertEqual([],calls); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
        for rel in (self.plan["route_binding"]["decision_path"],sd0.STATIC_PATHS[1],sd0.STATIC_PATHS[2],sd0.STATIC_PATHS[0]):
            self.tearDown(); self.setUp(); ready=self.ready_preflight(); self.persist_ready(ready); (self.root/rel).write_bytes(b"drift"); calls=[]
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
            self.assertEqual([],calls,rel); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
        for git_value in ("bad-branch","0"*40):
            self.tearDown(); self.setUp(); ready=self.ready_preflight()
            with self.client_context(), patch.object(sd0,"_git",return_value=git_value), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
            self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())
            self.tearDown(); self.setUp(); ready=self.ready_preflight(); self.persist_ready(ready); calls=[]
            with self.client_context(), patch.object(sd0,"_git",return_value=git_value), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
            self.assertEqual([],calls); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
        self.tearDown(); self.setUp(); ready=self.ready_preflight(); self.persist_ready(ready); drift=self.root/sd0.NETWORK_PATHS[0]; drift.parent.mkdir(parents=True,exist_ok=True); drift.write_bytes(b"drift"); calls=[]
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
        self.assertEqual([],calls); self.assertEqual(b"drift",drift.read_bytes())
        self.tearDown(); self.setUp(); ready=self.ready_preflight(); drift=self.root/sd0.NETWORK_PATHS[0]; drift.parent.mkdir(parents=True,exist_ok=True); drift.write_bytes(b"drift")
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
        self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists()); self.assertEqual(b"drift",drift.read_bytes())
        for entry in ("persist","execute"):
            self.tearDown(); self.setUp(); contract=copy.deepcopy(self.runtime_contract); authority=self.root/"authority.txt"; authority.write_bytes(b"good"); contract["authority_bindings"]=[{"path":"authority.txt","physical_sha256":sd0._sha(b"good")}]
            self.materialize_static_inputs(); self.materialize_empty_output_parents()
            with self.client_context(contract=contract), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                ready=sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True)
            self.assertIsInstance(ready,sd0.ReadyPreflight)
            if entry=="persist":
                authority.write_bytes(b"drift")
                with self.client_context(contract=contract), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
                self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())
            else:
                with self.client_context(contract=contract): sd0.persist_ready(self.root,ready)
                authority.write_bytes(b"drift2"); calls=[]
                with self.client_context(contract=contract), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
                self.assertEqual([],calls); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
        for entry in ("persist","execute"):
            self.tearDown(); self.setUp(); ready=self.ready_preflight()
            if entry=="execute": self.persist_ready(ready)
            old=Path(str(self.root)+"-inode-old"); self.root.rename(old); shutil.copytree(old,self.root); old_inode=sd0._READY[ready.digest][1]["root_inode"]; new_inode=self.root.stat().st_ino
            try:
                self.assertEqual(str(self.root.resolve()),sd0._READY[ready.digest][1]["resolved_root"]); self.assertNotEqual(old_inode,new_inode)
                if entry=="persist":
                    with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready)
                    self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists())
                else:
                    calls=[]
                    with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda s:calls.append(s))
                    self.assertEqual([],calls); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))
            finally:
                shutil.rmtree(old)

    def test_r5_t28_unpatched_r3_r4_r5_gate_stays_before_public_entrypoints(self) -> None:
        calls=[]; forged=sd0.ReadyPreflight(b"{}","0"*64)
        for call in (lambda:sd0.main(["--tests-evidence","none"]),lambda:sd0.preflight(REPOSITORY,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append(1)),lambda:sd0.persist_ready(REPOSITORY,forged),lambda:sd0.execute(REPOSITORY,ready=forged,opener=lambda _:calls.append(2))):
            with self.assertRaises(sd0.SD0Error): call()
        self.assertEqual([],calls)

    def test_r5_t29_post_status_header_exception_keeps_status_without_header_record(self) -> None:
        self.assert_integrated_header_failure(False)

    def test_r5_t30_header_prefix_digest_survives_iterator_failure(self) -> None:
        self.assert_integrated_header_failure(True)

    def test_r5_t31_nonbytes_body_keeps_complete_header_evidence(self) -> None:
        ready=self.ready_preflight(); self.persist_ready(ready); reply=sd0.HttpResponse(200,(("Content-Length","5"),("Content-Type","text/plain")),object())
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda _:reply)
        row=json.loads((self.root/sd0.NETWORK_PATHS[0]).read_text().splitlines()[0]); self.assertEqual(200,row["status_code"]); self.assertEqual(0,row["response_body_bytes"]); self.assertEqual("TypeError",row["error_class"]); self.assertTrue((self.root/sd0.NETWORK_PATHS[1]).read_bytes())

    def test_r5_t32_cleanup_terminal_preserves_head_application_capture(self) -> None:
        """R5-T32 is an integrated cleanup contract, not an observation unit test."""
        class ResponseCloseError(RuntimeError):
            pass

        class ConnectionCloseError(RuntimeError):
            pass

        cases = (
            ("head-response", self.specs[0], "response", None),
            ("head-connection", self.specs[0], "connection", None),
            ("head-both", self.specs[0], "both", None),
            ("get-response", self.specs[1], "response", None),
            ("get-connection", self.specs[1], "connection", None),
            ("get-both", self.specs[1], "both", None),
            ("head-response-memory", self.specs[0], "response-base", MemoryError("head response close")),
            ("get-connection-keyboard", self.specs[1], "connection-base", KeyboardInterrupt("get connection close")),
        )
        for name, spec, mode, base_error in cases:
            with self.subTest(case=name):
                self.tearDown()
                self.setUp()
                ready = self.ready_preflight()
                self.persist_ready(ready)
                closes: list[str] = []
                calls: list[str] = []
                reads: list[int] = []
                wraps: list[object] = []
                body = b"" if spec.method == "HEAD" else b"r5-t32-get-payload"
                declared = 42 if spec.method == "HEAD" else len(body)
                headers = (("Content-Length", str(declared)), ("Content-Type", "text/plain"))

                class Response:
                    status = 200

                    def getheaders(self):
                        return list(headers)

                    def read(self, amount: int) -> bytes:
                        reads.append(amount)
                        if spec.method == "HEAD":
                            raise AssertionError("HEAD must not read an application body")
                        return body

                    def close(self) -> None:
                        closes.append("response")
                        if mode in ("response", "both"):
                            raise ResponseCloseError("ordinary response close")
                        if mode == "response-base":
                            raise base_error

                class Connection:
                    instances = 0

                    def __init__(self, *_args, **_kwargs) -> None:
                        type(self).instances += 1
                        self.sock = object()

                    def set_tunnel(self, *_args) -> None:
                        return None

                    def connect(self) -> None:
                        return None

                    def putrequest(self, *_args, **_kwargs) -> None:
                        return None

                    def putheader(self, *_args, **_kwargs) -> None:
                        return None

                    def endheaders(self) -> None:
                        return None

                    def getresponse(self) -> Response:
                        calls.append(spec.request_id)
                        return Response()

                    def close(self) -> None:
                        closes.append("connection")
                        if mode in ("connection", "both"):
                            raise ConnectionCloseError("ordinary connection close")
                        if mode == "connection-base":
                            raise base_error

                class Context:
                    def wrap_socket(self, sock, **_kwargs):
                        wraps.append(sock)
                        return sock

                with self.client_context(), patch.object(sd0, "_load", return_value=(self.runtime_contract, self.plan, (spec,))), patch.object(sd0.http.client, "HTTPConnection", Connection), patch.object(sd0.ssl, "create_default_context", return_value=Context()):
                    if base_error is None:
                        with self.assertRaises(sd0.SD0Error) as raised:
                            sd0.execute(self.root, ready=ready)
                    else:
                        with self.assertRaises(type(base_error)) as raised:
                            sd0.execute(self.root, ready=ready)

                self.assertEqual([spec.request_id], calls)
                self.assertEqual(1, Connection.instances)
                self.assertEqual(1, len(wraps))
                self.assertEqual(["response", "connection"], closes)
                self.assertEqual([] if spec.method == "HEAD" else [declared], reads)
                if base_error is not None:
                    self.assertIs(base_error, raised.exception)
                    self.assertEqual(b"", (self.root / sd0.NETWORK_PATHS[0]).read_bytes())
                    self.assertEqual(b"", (self.root / sd0.NETWORK_PATHS[1]).read_bytes())
                    self.assertTrue(all(not (self.root / path).exists() for path in sd0.NETWORK_PATHS[2:]))
                    continue

                self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE", raised.exception.state)
                request = json.loads((self.root / sd0.NETWORK_PATHS[0]).read_text())
                header = json.loads((self.root / sd0.NETWORK_PATHS[1]).read_text())
                evidence = sd0._canon([[key, value] for key, value in headers])
                self.assertEqual(200, request["status_code"])
                self.assertEqual("VALIDATED", request["tls_validation_result"])
                self.assertEqual(len(body), request["response_body_bytes"])
                self.assertEqual(sd0._sha(body), request["response_body_sha256"])
                self.assertEqual(sd0._sha(evidence), request["response_headers_sha256"])
                self.assertEqual("ConnectionCloseError" if mode == "connection" else "ResponseCloseError", request["error_class"])
                self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE", request["terminal_disposition"])
                self.assertEqual([[key, value] for key, value in headers], header["headers"])
                self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE", header["terminal_disposition"])
                closure = json.loads((self.root / sd0.NETWORK_PATHS[6]).read_text())
                inventory = json.loads((self.root / sd0.NETWORK_PATHS[7]).read_text())
                self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE", closure["terminal_disposition"])
                self.assertEqual("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE", closure["failure_state"])
                self.assertTrue(inventory["allowlist_match"])
                self.assertTrue(all((self.root / path).exists() for path in (sd0.NETWORK_PATHS[0], sd0.NETWORK_PATHS[1], sd0.NETWORK_PATHS[6], sd0.NETWORK_PATHS[7])))
                self.assertTrue(all(not (self.root / path).exists() for path in sd0.NETWORK_PATHS[2:6]))

    def test_r6_t33_nested_context_rehash_needs_independent_expected(self) -> None:
        leaves,structural=self.assert_full_context_mutation_matrix(); self.assertGreater(leaves,20); self.assertGreater(structural,5)

    def test_r6_t34_bad_local_context_never_calls_tcp(self) -> None:
        self.materialize_static_inputs(); self.materialize_empty_output_parents(); calls=[]
        git_calls=[]
        def git(_root,*args):
            git_calls.append(args[0])
            if len(git_calls)==1: return self.plan["route_binding"]["branch"]
            if len(git_calls)==2: return self.plan["route_binding"]["head"]
            return "unauthorized-branch" if args[0]=="branch" else "0"*40
        with self.client_context(), patch.object(sd0,"_git",side_effect=git), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)), self.assertRaises(sd0.SD0Error):
            sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append(1) or True)
        self.assertEqual(["branch","rev-parse","branch","rev-parse"],git_calls); self.assertEqual([],calls); self.assertFalse(sd0._READY); self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists()); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS))

    def test_r6_t35_missing_route_precedes_tcp(self) -> None:
        self.assert_route_failure_matrix()

    def test_r6_t36_forged_document_rejects_persist(self) -> None:
        for key,forged,context in self.forged_ready_variants():
            with sd0._CAPABILITY_LOCK: sd0._READY[forged.digest]=(forged._snapshot,context)
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,forged)
            self.assertFalse((self.root/sd0.PREFLIGHT_PATH).exists(),key)

    def test_r6_t37_forged_document_rejects_execute_before_opener(self) -> None:
        for key,forged,context in self.forged_ready_variants():
            with sd0._CAPABILITY_LOCK: sd0._READY[forged.digest]=(forged._snapshot,context)
            (self.root/sd0.PREFLIGHT_PATH).write_bytes(forged._snapshot+b"\n"); calls=[]
            with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=forged,opener=lambda s:calls.append(s))
            self.assertEqual([],calls,key); self.assertFalse(any((self.root/p).exists() for p in sd0.NETWORK_PATHS),key); (self.root/sd0.PREFLIGHT_PATH).unlink()

    def test_r6_t38_integrated_header_failure_contract(self) -> None:
        self.assert_integrated_header_failure(False)
        self.tearDown()
        self.setUp()
        self.assert_integrated_header_failure(True)

    def test_r6_t39_cleanup_ordinary_failures_use_real_execute_boundary(self) -> None:
        """R6-T39: eight fresh-root execute cases across the actual opener boundary.

        The request tuple is intentionally reduced to one frozen ``Spec`` per
        subcase only after READY has been issued.  That keeps every assertion
        focused on the failing logical request while still exercising
        ``execute -> StdlibProxyOpener -> HTTPConnection/TLS -> finally``.  A
        direct ``HttpResponse`` or ``_make_observation`` would not cover the
        cleanup protocol and is therefore prohibited here.
        """
        class ResponseCloseError(RuntimeError):
            pass

        class ConnectionCloseError(RuntimeError):
            pass

        cases = (
            # HEAD/GET x response-only, connection-only, and both ordinary
            # cleanup errors.  The normal response has no substantive state,
            # so the first cleanup error must become the sealed STOP state.
            ("head-response", self.specs[0], "response", None),
            ("head-connection", self.specs[0], "connection", None),
            ("head-both", self.specs[0], "both", None),
            ("get-response", self.specs[1], "response", None),
            ("get-connection", self.specs[1], "connection", None),
            ("get-both", self.specs[1], "both", None),
            # Existing response outcomes must win over later ordinary cleanup
            # errors: a non-200 HEAD and an incomplete GET body respectively.
            ("head-existing-state", self.specs[0], "both", "head-status"),
            ("get-existing-state", self.specs[1], "both", "get-incomplete"),
        )
        for name, spec, close_mode, existing in cases:
            with self.subTest(case=name):
                self.tearDown()
                self.setUp()
                ready = self.ready_preflight()
                self.persist_ready(ready)
                closes: list[str] = []
                calls: list[str] = []
                reads: list[int] = []
                status = 500 if existing == "head-status" else 200
                body = b"" if spec.method == "HEAD" else b"get-clean-payload"
                if existing == "get-incomplete":
                    body = b"get-partial-payload"
                declared = len(body) + 7 if existing == "get-incomplete" else (42 if spec.method == "HEAD" else len(body))
                headers = (("Content-Length", str(declared)), ("Content-Type", "text/plain"))

                class Response:
                    def __init__(self) -> None:
                        self.status = status

                    def getheaders(self):
                        return list(headers)

                    def read(self, amount: int) -> bytes:
                        reads.append(amount)
                        if spec.method == "HEAD":
                            raise AssertionError("HEAD must never read an application body")
                        if existing == "get-incomplete":
                            raise http.client.IncompleteRead(body, declared)
                        return body

                    def close(self) -> None:
                        closes.append("response")
                        if close_mode in ("response", "both"):
                            raise ResponseCloseError("response close")

                class Connection:
                    instances = 0

                    def __init__(self, *_args, **_kwargs) -> None:
                        type(self).instances += 1
                        self.sock = object()

                    def set_tunnel(self, *_args) -> None:
                        return None

                    def connect(self) -> None:
                        return None

                    def putrequest(self, *_args, **_kwargs) -> None:
                        return None

                    def putheader(self, *_args, **_kwargs) -> None:
                        return None

                    def endheaders(self) -> None:
                        return None

                    def getresponse(self) -> Response:
                        calls.append(spec.request_id)
                        return Response()

                    def close(self) -> None:
                        closes.append("connection")
                        if close_mode in ("connection", "both"):
                            raise ConnectionCloseError("connection close")

                class Context:
                    def wrap_socket(self, sock, **_kwargs):
                        return sock

                expected_state = (
                    "HALT_PROTOCOL_VIOLATION" if existing == "head-status"
                    else "WAIT_DATA_NO_FALLBACK" if existing == "get-incomplete"
                    else "STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE"
                )
                expected_error = (
                    "SD0Error" if existing == "head-status"
                    else "IncompleteRead" if existing == "get-incomplete"
                    else "ConnectionCloseError" if close_mode == "connection"
                    else "ResponseCloseError"
                )
                with self.client_context(), patch.object(sd0, "_load", return_value=(self.runtime_contract, self.plan, (spec,))), patch.object(sd0.http.client, "HTTPConnection", Connection), patch.object(sd0.ssl, "create_default_context", return_value=Context()), self.assertRaises(sd0.SD0Error) as raised:
                    sd0.execute(self.root, ready=ready)

                self.assertEqual(expected_state, raised.exception.state)
                self.assertEqual([spec.request_id], calls)
                self.assertEqual(1, Connection.instances)
                self.assertEqual(["response", "connection"], closes)
                self.assertEqual(0 if spec.method == "HEAD" else 1, len(reads))
                if spec.method == "GET":
                    self.assertEqual(declared, reads[0])
                else:
                    self.assertEqual([], reads)

                request_rows = (self.root / sd0.NETWORK_PATHS[0]).read_text().splitlines()
                header_rows = (self.root / sd0.NETWORK_PATHS[1]).read_text().splitlines()
                self.assertEqual(1, len(request_rows))
                self.assertEqual(1, len(header_rows))
                request = json.loads(request_rows[0])
                header = json.loads(header_rows[0])
                evidence = sd0._canon([[key, value] for key, value in headers])
                self.assertEqual(spec.request_id, request["request_id"])
                self.assertEqual(spec.method, request["method"])
                self.assertEqual(status, request["status_code"])
                self.assertEqual("VALIDATED", request["tls_validation_result"])
                self.assertEqual(len(body), request["response_body_bytes"])
                self.assertEqual(sd0._sha(body), request["response_body_sha256"])
                self.assertEqual(sd0._sha(evidence), request["response_headers_sha256"])
                self.assertEqual(expected_error, request["error_class"])
                self.assertEqual(expected_state, request["terminal_disposition"])
                self.assertEqual([[key, value] for key, value in headers], header["headers"])
                self.assertEqual(len(evidence), header["header_bytes"])
                self.assertEqual(sd0._sha(evidence), header["headers_sha256"])
                self.assertEqual(expected_state, header["terminal_disposition"])

                closure = json.loads((self.root / sd0.NETWORK_PATHS[6]).read_text())
                inventory = json.loads((self.root / sd0.NETWORK_PATHS[7]).read_text())
                self.assertEqual(expected_state, closure["terminal_disposition"])
                self.assertEqual(expected_state, closure["failure_state"])
                self.assertEqual([], closure["document_identities"])
                self.assertEqual(sd0._sha((self.root / sd0.NETWORK_PATHS[0]).read_bytes()), closure["request_ledger_sha256"])
                self.assertEqual(sd0._sha((self.root / sd0.NETWORK_PATHS[1]).read_bytes()), closure["response_header_ledger_sha256"])
                self.assertTrue(inventory["allowlist_match"])
                self.assertEqual(0, inventory["outside_allowlist_count"])
                self.assertEqual(0, inventory["market_row_body_artifact_count"])
                self.assertEqual(0, inventory["zip_body_artifact_count"])
                self.assertEqual(list(sd0.NETWORK_PATHS[:2]) + [sd0.NETWORK_PATHS[6]], [item["path"] for item in inventory["artifact_identities"]])
                self.assertTrue(all((self.root / path).exists() for path in (sd0.NETWORK_PATHS[0], sd0.NETWORK_PATHS[1], sd0.NETWORK_PATHS[6], sd0.NETWORK_PATHS[7])))
                self.assertTrue(all(not (self.root / path).exists() for path in sd0.NETWORK_PATHS[2:6]))

    def test_r6_t40_baseexception_cleanup_matrix_uses_real_execute_boundary(self) -> None:
        """R6-T40: all closer BaseException permutations through ``execute``.

        BaseExceptions must leave the actual opener after it has attempted both
        closers.  They deliberately bypass ``execute``'s ordinary sealing
        path, so the only permitted outputs are the two empty ledgers created
        before the one logical request; no closure or inventory may claim a
        completed STOP result.
        """
        class OrdinaryResponseCloseError(RuntimeError):
            pass

        class OrdinaryConnectionCloseError(RuntimeError):
            pass

        def assert_unsealed_after_baseexception(
            *,
            name: str,
            spec: sd0.Spec,
            response_close: BaseException | None = None,
            connection_close: BaseException | None = None,
            body_phase: BaseException | None = None,
            expected: BaseException,
        ) -> None:
            self.tearDown()
            self.setUp()
            ready = self.ready_preflight()
            self.persist_ready(ready)
            closes: list[str] = []
            opens: list[str] = []
            reads: list[int] = []
            wraps: list[object] = []
            body = b"body-phase-payload" if spec.method == "GET" else b""
            headers = (("Content-Length", str(len(body) if spec.method == "GET" else 42)), ("Content-Type", "text/plain"))

            class Response:
                status = 200

                def getheaders(self):
                    return list(headers)

                def read(self, amount: int) -> bytes:
                    reads.append(amount)
                    if body_phase is not None:
                        raise body_phase
                    return body

                def close(self) -> None:
                    closes.append("response")
                    if response_close is not None:
                        raise response_close

            class Connection:
                instances = 0

                def __init__(self, *_args, **_kwargs) -> None:
                    type(self).instances += 1
                    self.sock = object()

                def set_tunnel(self, *_args) -> None:
                    return None

                def connect(self) -> None:
                    return None

                def putrequest(self, *_args, **_kwargs) -> None:
                    return None

                def putheader(self, *_args, **_kwargs) -> None:
                    return None

                def endheaders(self) -> None:
                    return None

                def getresponse(self) -> Response:
                    opens.append(spec.request_id)
                    return Response()

                def close(self) -> None:
                    closes.append("connection")
                    if connection_close is not None:
                        raise connection_close

            class Context:
                def wrap_socket(self, sock, **_kwargs):
                    wraps.append(sock)
                    return sock

            with self.client_context(), patch.object(sd0, "_load", return_value=(self.runtime_contract, self.plan, (spec,))), patch.object(sd0.http.client, "HTTPConnection", Connection), patch.object(sd0.ssl, "create_default_context", return_value=Context()):
                with self.assertRaises(type(expected), msg=name) as raised:
                    sd0.execute(self.root, ready=ready)
            self.assertIs(expected, raised.exception, name)
            self.assertEqual([spec.request_id], opens, name)
            self.assertEqual(1, Connection.instances, name)
            self.assertEqual(1, len(wraps), name)
            self.assertEqual(["response", "connection"], closes, name)
            self.assertEqual([len(body)] if spec.method == "GET" else [], reads, name)

            # A BaseException bypasses both normal SD0Error conversion and the
            # closure report.  execute creates its two ledgers before opening,
            # but neither can contain a fabricated STOP terminal record.
            self.assertTrue((self.root / sd0.NETWORK_PATHS[0]).exists(), name)
            self.assertTrue((self.root / sd0.NETWORK_PATHS[1]).exists(), name)
            self.assertEqual(b"", (self.root / sd0.NETWORK_PATHS[0]).read_bytes(), name)
            self.assertEqual(b"", (self.root / sd0.NETWORK_PATHS[1]).read_bytes(), name)
            self.assertTrue(all(not (self.root / path).exists() for path in sd0.NETWORK_PATHS[2:]), name)

        base_types = (MemoryError, KeyboardInterrupt, SystemExit, GeneratorExit)
        for base_type in base_types:
            with self.subTest(stage="closer", error=base_type.__name__, placement="response-only"):
                response = base_type("response-first")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-response", spec=self.specs[0], response_close=response, expected=response)
            with self.subTest(stage="closer", error=base_type.__name__, placement="connection-only"):
                connection = base_type("connection-first")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-connection", spec=self.specs[0], connection_close=connection, expected=connection)
            with self.subTest(stage="closer", error=base_type.__name__, placement="both"):
                response = base_type("response-first")
                connection = base_type("connection-second")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-both", spec=self.specs[0], response_close=response, connection_close=connection, expected=response)
            with self.subTest(stage="closer", error=base_type.__name__, placement="ordinary-response-base-connection"):
                connection = base_type("connection-base")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-ordinary-response-base-connection", spec=self.specs[0], response_close=OrdinaryResponseCloseError("ordinary response"), connection_close=connection, expected=connection)
            with self.subTest(stage="closer", error=base_type.__name__, placement="base-response-ordinary-connection"):
                response = base_type("response-base")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-base-response-ordinary-connection", spec=self.specs[0], response_close=response, connection_close=OrdinaryConnectionCloseError("ordinary connection"), expected=response)

        # Body-phase BaseExceptions must keep their original identity when
        # cleanup itself succeeds.  This is deliberately a distinct phase from
        # the 20 closer combinations above.
        for base_type in base_types:
            with self.subTest(stage="body", error=base_type.__name__):
                body = base_type("body-phase")
                assert_unsealed_after_baseexception(name=f"{base_type.__name__}-body", spec=self.specs[1], body_phase=body, expected=body)

    def _r7_gate_root(self) -> Path:
        """Build a private, byte-for-byte authority tree for real gate tests."""
        gate_root = self.root / "r7-gate-authorities"
        for relative in (
            sd0.R3_DECISION_PATH, sd0.R4_DECISION_PATH, sd0.R5_DECISION_PATH,
            sd0.R6_DECISION_PATH, sd0.R6_COMPLETION_PATH, sd0.R7_DECISION_PATH,
        ):
            target = gate_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY / relative).read_bytes())
        return gate_root

    def _assert_no_r7_outputs(self, root: Path, calls: list[str]) -> None:
        self.assertEqual([], calls)
        self.assertFalse((root / sd0.PREFLIGHT_PATH).exists())
        self.assertTrue(all(not (root / path).exists() for path in sd0.NETWORK_PATHS))

    def test_r7_t41_authentic_chain_still_suspends_every_production_entrypoint(self) -> None:
        """R7-T41: real R3--R7 gate validates then stops before all side effects."""
        gate_root = self._r7_gate_root()
        calls: list[str] = []
        forged = sd0.ReadyPreflight(b"{}", "0" * 64)
        with patch.object(sd0, "ROOT", gate_root):
            for name, call in (
                ("main", lambda: sd0.main(["--tests-evidence", "not-read.json"])),
                ("preflight", lambda: sd0.preflight(gate_root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: calls.append("tcp"))),
                ("persist", lambda: sd0.persist_ready(gate_root, forged)),
                ("execute", lambda: sd0.execute(gate_root, ready=forged, opener=lambda _spec: calls.append("opener"))),
            ):
                with self.subTest(entrypoint=name), self.assertRaises(sd0.SD0Error) as raised:
                    call()
                self.assertEqual("WAIT_DATA_NO_FALLBACK", raised.exception.state)
        self._assert_no_r7_outputs(gate_root, calls)

    def test_r7_t42_completion_and_r7_drift_fail_before_callbacks_or_outputs(self) -> None:
        """R7-T42: copies only; every authority failure retains workspace bytes."""
        workspace_bytes = {
            relative: (REPOSITORY / relative).read_bytes()
            for relative in (sd0.R6_COMPLETION_PATH, sd0.R7_DECISION_PATH)
        }
        forged = sd0.ReadyPreflight(b"{}", "0" * 64)
        for relative in (sd0.R6_COMPLETION_PATH, sd0.R7_DECISION_PATH):
            for variant in ("missing", "malformed", "drift"):
                with self.subTest(authority=relative, variant=variant):
                    gate_root = self._r7_gate_root()
                    target = gate_root / relative
                    if variant == "missing":
                        target.unlink()
                    elif variant == "malformed":
                        target.write_bytes(b"{")
                    else:
                        original = target.read_bytes()
                        target.write_bytes(original[:-1] + bytes((original[-1] ^ 1,)))
                    calls: list[str] = []
                    with patch.object(sd0, "ROOT", gate_root):
                        with self.assertRaises(sd0.SD0Error) as preflight_raised:
                            sd0.preflight(gate_root, tests_evidence=TEST_EVIDENCE, tcp_probe=lambda *_: calls.append("tcp"))
                        with self.assertRaises(sd0.SD0Error) as execute_raised:
                            sd0.execute(gate_root, ready=forged, opener=lambda _spec: calls.append("opener"))
                    self.assertEqual("WAIT_DATA_NO_FALLBACK", preflight_raised.exception.state)
                    self.assertEqual("WAIT_DATA_NO_FALLBACK", execute_raised.exception.state)
                    self._assert_no_r7_outputs(gate_root, calls)
                    self.assertEqual(workspace_bytes[relative], (REPOSITORY / relative).read_bytes())

    def _r8_gate_root(self) -> Path:
        self._authority_counter += 1
        root = self.root / f"r8-gate-authorities-{self._authority_counter}"
        for relative in (
            sd0.R3_DECISION_PATH, sd0.R4_DECISION_PATH, sd0.R5_DECISION_PATH, sd0.R6_DECISION_PATH,
            sd0.R6_COMPLETION_PATH, sd0.R7_DECISION_PATH, sd0.R7_COMPLETION_PATH, sd0.R8_DECISION_PATH,
            sd0.STATIC_PATHS[3], sd0.STATIC_PATHS[4],
        ):
            target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY / relative).read_bytes())
        return root.resolve()

    def _r8_runtime_root(self) -> Path:
        root=self._r8_gate_root()
        contract=sd0._strict_json(CONTRACT_PATH.read_bytes())
        paths=set(sd0.STATIC_PATHS[:3])|{sd0.ROUTE_BINDING["decision_path"]}|{item["path"] for item in contract["authority_bindings"]}
        for relative in paths:
            target=root/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((REPOSITORY/relative).read_bytes())
        for relative in (sd0.PREFLIGHT_PATH,)+sd0.NETWORK_PATHS: (root/relative).parent.mkdir(parents=True,exist_ok=True)
        return root

    def _r8_runtime_context(self,root:Path):
        # These R8 cases isolate runtime capability and callback handling.  The
        # authority-drift paths are exercised separately, so use the same
        # authority-free runtime contract fixture as the earlier client tests.
        runtime_plan = sd0._strict_json((root / sd0.STATIC_PATHS[2]).read_bytes())
        runtime_specs = sd0._validate_plan(runtime_plan)
        return patch.multiple(
            sd0,
            WORKSPACE=str(root.resolve()),
            _git=lambda _root, *args: sd0.AUTH_BRANCH if args[0] == "branch" else sd0.AUTH_HEAD,
            _load=lambda _safe: (self.runtime_contract, runtime_plan, runtime_specs),
        )

    def _r8_completion(self, root: Path, **replace: object) -> tuple[bytes, str, str]:
        self._activation_counter += 1
        client, test = sd0._identity(root, sd0.STATIC_PATHS[3]), sd0._identity(root, sd0.STATIC_PATHS[4])
        now = datetime.now(timezone.utc)
        doc: dict[str, object] = {
            "schema_version": sd0.R8_COMPLETION_SCHEMA, "decision_id": sd0.R8_COMPLETION_ID,
            "decision_state": sd0.R8_COMPLETION_STATE, "workspace_identity": {"cwd": sd0.AUTH_WORKSPACE, "branch": sd0.AUTH_BRANCH, "head": sd0.AUTH_HEAD},
            "authority_bindings": {"r8_authorization": {"path": sd0.R8_DECISION_PATH, "physical_sha256": sd0.R8_DECISION_PHYSICAL_SHA256, "canonical_sha256": sd0.R8_DECISION_SHA256, "decision_id": sd0.R8_DECISION_ID, "decision_state": sd0.R8_DECISION_STATE}},
            "post_patch_pair": {"client": client, "test": test, "exact_input_pair_sha256": sd0._pair_sha(client, test), "pair_formula": "sha256(client_path_utf8 || 0x00 || client_physical_sha256_ascii || 0x00 || test_path_utf8 || 0x00 || test_physical_sha256_ascii)"},
            "activation": {"unique_activation_id": "PITAR1-SD0-R8-ACT-" + f"{self._activation_counter:032x}", "not_before_utc": (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"), "expires_at_utc": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
            "permission_matrix": dict(sd0._PERMISSIONS),
            "frozen_bindings": {"route": {"physical_sha256": sd0.AUTH_ROUTE_DECISION_PHYSICAL_SHA256, "canonical_sha256": sd0.AUTH_ROUTE_DECISION_CANONICAL_SHA256}, "contract": {"physical_sha256": sd0.AUTH_CONTRACT_PHYSICAL_SHA256, "canonical_sha256": sd0.AUTH_CONTRACT_CANONICAL_SHA256}, "plan": {"physical_sha256": sd0.AUTH_PLAN_PHYSICAL_SHA256, "canonical_sha256": sd0.AUTH_PLAN_CANONICAL_SHA256}},
            "implementation_review": {"independent_reviews": [
                {"role":"SOURCE_MAP_REVIEW","reviewer":"independent-source-map-reviewer","decision":"ACCEPT"},
                {"role":"EXECUTED_PROBE_REVIEW","reviewer":"independent-executed-probe-reviewer","decision":"ACCEPT"},
            ]},
            "tests": copy.deepcopy(sd0._R8_TEST_EVIDENCE),
            "r8_cases": dict(sd0._R8_CASES),
            "workspace_output_absence": copy.deepcopy(sd0._WORKSPACE_OUTPUT_ABSENCE),
            "external_actions": dict(sd0._EXTERNAL_ACTIONS),
            "mutation_audit": copy.deepcopy(sd0._MUTATION_AUDIT),
            "precheck_safe": sd0._PRECHECK_SAFE,
            "execution_contract": copy.deepcopy(sd0._EXECUTION_CONTRACT),
            "decision_sha256": "",
        }
        doc.update(replace); doc["decision_sha256"] = sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion/v1", doc, "decision_sha256")
        raw = sd0._canon(doc); return raw, sd0._sha(raw), doc["decision_sha256"]  # type: ignore[return-value]

    def _mint_r8(self, root: Path) -> sd0._ActivationCapability:
        raw, physical, canonical = self._r8_completion(root)
        return sd0._mint_activation_capability(completion_raw_bytes=raw, expected_completion_physical_sha256=physical, expected_completion_canonical_sha256=canonical, exact_resolved_repository_root=root.resolve())

    def test_r8_t43_default_and_cli_without_capability_suspend_before_callbacks(self) -> None:
        for variant in ("absent completion","absent capability"):
            root=self._r8_gate_root(); calls=[]; forged=sd0.ReadyPreflight(b"{}","0"*64)
            if variant=="absent completion":
                with self.assertRaises(sd0.SD0Error):
                    sd0._mint_activation_capability(completion_raw_bytes=None,expected_completion_physical_sha256="0"*64,expected_completion_canonical_sha256="0"*64,exact_resolved_repository_root=root.resolve())  # type: ignore[arg-type]
            with patch.object(sd0,"ROOT",root):
                entries=(
                    ("main",lambda:sd0.main(["--tests-evidence","never-read.json"])),
                    ("preflight",lambda:sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append("tcp"))),
                    ("persist",lambda:sd0.persist_ready(root,forged)),
                    ("execute",lambda:sd0.execute(root,ready=forged,opener=lambda _:calls.append("opener"))),
                )
                for entry,call in entries:
                    with self.subTest(variant=variant,entry=entry),self.assertRaises(sd0.SD0Error) as raised: call()
                    self.assertEqual("WAIT_DATA_NO_FALLBACK",raised.exception.state)
            self._assert_no_r7_outputs(root,calls)

    def test_r8_t44_r7_completion_and_r8_authority_fail_closed(self) -> None:
        repair_variants=("missing","symlink","directory","malformed","duplicate key","physical drift","canonical drift","wrong id","wrong state","wrong workspace")
        repairs=(
            ("R3",sd0.R3_DECISION_PATH,"R3_DECISION_PHYSICAL_SHA256","R3_DECISION_SHA256","msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r3-repair/v1"),
            ("R4",sd0.R4_DECISION_PATH,"R4_DECISION_PHYSICAL_SHA256","R4_DECISION_SHA256","msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r4-repair/v1"),
            ("R5",sd0.R5_DECISION_PATH,"R5_DECISION_PHYSICAL_SHA256","R5_DECISION_SHA256","msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r5-repair/v1"),
            ("R6",sd0.R6_DECISION_PATH,"R6_DECISION_PHYSICAL_SHA256","R6_DECISION_SHA256","msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r6-repair/v1"),
        )
        for authority,relative,physical_name,canonical_name,domain in repairs:
            for variant in repair_variants:
                root=self._r8_gate_root(); target=root/relative; stack=ExitStack()
                if variant=="missing": target.unlink()
                elif variant=="symlink":
                    raw=target.read_bytes(); target.unlink(); sibling=root/f"{authority.lower()}-exact-bytes.json"; sibling.write_bytes(raw); os.symlink(sibling,target)
                elif variant=="directory": target.unlink(); target.mkdir()
                elif variant=="malformed":
                    raw=b"{"; target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                elif variant=="duplicate key":
                    raw=b'{"decision_id":"a","decision_id":"b"}'; target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                elif variant=="physical drift":
                    raw=target.read_bytes(); target.write_bytes(raw[:-1]+bytes((raw[-1]^1,)))
                else:
                    doc=sd0._strict_json(target.read_bytes())
                    if variant=="canonical drift": doc["decision_sha256"]="0"*64
                    elif variant=="wrong id": doc["decision_id"]="WRONG"
                    elif variant=="wrong state": doc["decision_state"]="WRONG"
                    else: doc["workspace_identity"]["cwd"]="/wrong"
                    if variant!="canonical drift":
                        doc["decision_sha256"]=sd0._self(domain,doc,"decision_sha256")
                        stack.enter_context(patch.object(sd0,canonical_name,doc["decision_sha256"]))
                    raw=sd0._canon(doc); target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                callbacks=[]
                with self.subTest(authority=authority,variant=variant),stack,patch.object(sd0,"_validate_completion",wraps=sd0._validate_completion) as completion_validator,patch.object(sd0,"_tcp",side_effect=lambda *_:callbacks.append("tcp")),patch.object(sd0,"StdlibProxyOpener",side_effect=lambda:callbacks.append("opener")),self.assertRaises(sd0.SD0Error) as raised:
                    self._mint_r8(root)
                self.assertEqual("WAIT_DATA_NO_FALLBACK",raised.exception.state,(authority,variant))
                self.assertEqual(0,completion_validator.call_count,(authority,variant))
                self.assertEqual([],callbacks,(authority,variant))
                self.assertFalse(sd0._CAPABILITIES,(authority,variant))
                self.assertFalse(any((root/p).exists() for p in (sd0.PREFLIGHT_PATH,)+sd0.NETWORK_PATHS),(authority,variant))

        variants = ("missing","symlink","directory","malformed","duplicate key","physical drift","canonical drift","wrong id","wrong state","wrong workspace","wrong predecessor","wrong permission boundary")
        authorities = (
            ("R7 completion", sd0.R7_COMPLETION_PATH, "R7_COMPLETION_PHYSICAL_SHA256", "R7_COMPLETION_SHA256", "msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r7-gate-rebinding-completion/v1"),
            ("R8", sd0.R8_DECISION_PATH, "R8_DECISION_PHYSICAL_SHA256", "R8_DECISION_SHA256", "msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route/v1"),
        )
        for authority, relative, physical_name, canonical_name, domain in authorities:
            for variant in variants:
                root = self._r8_gate_root(); target = root / relative; stack = ExitStack()
                if variant == "missing": target.unlink()
                elif variant == "symlink":
                    raw = target.read_bytes(); target.unlink(); sibling = root / f"{authority.lower().replace(' ','-')}-real.json"; sibling.write_bytes(raw); os.symlink(sibling, target)
                elif variant == "directory": target.unlink(); target.mkdir()
                elif variant == "malformed":
                    raw=b"{"; target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                elif variant == "duplicate key":
                    raw=b'{"decision_id":"a","decision_id":"b"}'; target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                elif variant == "physical drift":
                    raw=target.read_bytes(); target.write_bytes(raw[:-1]+bytes((raw[-1]^1,)))
                else:
                    doc=sd0._strict_json(target.read_bytes())
                    if variant == "canonical drift": doc["decision_sha256"]="0"*64
                    elif variant == "wrong id": doc["decision_id"]="WRONG"
                    elif variant == "wrong state": doc["decision_state"]="WRONG"
                    elif variant == "wrong workspace": doc["workspace_identity"]["cwd"]="/wrong"
                    elif variant == "wrong predecessor":
                        key="r7_gate_rebinding_authorization" if authority=="R7 completion" else "accepted_r7_completion"
                        doc["authority_bindings"][key]["path"]="wrong.json"
                    elif authority=="R7 completion": doc["permission_matrix"]["production_preflight"]=True
                    else: doc["permission_matrix"]["production_preflight_now"]=True
                    if variant != "canonical drift":
                        doc["decision_sha256"]=sd0._self(domain,doc,"decision_sha256")
                        stack.enter_context(patch.object(sd0,canonical_name,doc["decision_sha256"]))
                    raw=sd0._canon(doc); target.write_bytes(raw); stack.enter_context(patch.object(sd0,physical_name,sd0._sha(raw)))
                callbacks=[]
                with self.subTest(authority=authority,variant=variant), stack, patch.object(sd0,"_validate_completion",wraps=sd0._validate_completion) as completion_validator, patch.object(sd0,"_tcp",side_effect=lambda *_:callbacks.append("tcp")), patch.object(sd0,"StdlibProxyOpener",side_effect=lambda:callbacks.append("opener")), self.assertRaises(sd0.SD0Error) as raised:
                    self._mint_r8(root)
                self.assertEqual("WAIT_DATA_NO_FALLBACK", raised.exception.state,(authority,variant))
                self.assertEqual(0,completion_validator.call_count,(authority,variant))
                self.assertEqual([],callbacks,(authority,variant))
                self.assertFalse(sd0._CAPABILITIES,(authority,variant))
                self.assertFalse(any((root/p).exists() for p in (sd0.PREFLIGHT_PATH,)+sd0.NETWORK_PATHS),(authority,variant))

    def test_r8_t45_external_completion_requires_two_independent_digests(self) -> None:
        variants=("missing expected physical digest","missing expected canonical digest","invalid digest syntax","physical mismatch before JSON reliance","malformed JSON","duplicate key","self canonical mismatch","external canonical mismatch","wrong schema","wrong decision id","non-accept state","missing activation id","malformed activation id","not-before in future","expired completion","window longer than 86400 seconds")
        for variant in variants:
            root=self._r8_gate_root(); raw,physical,canonical=self._r8_completion(root); doc=sd0._strict_json(raw)
            if variant=="missing expected physical digest": physical=""
            elif variant=="missing expected canonical digest": canonical=""
            elif variant=="invalid digest syntax": physical="G"*64
            elif variant=="physical mismatch before JSON reliance": raw=b"{"; physical="0"*64
            elif variant=="malformed JSON": raw=b"{"; physical=sd0._sha(raw)
            elif variant=="duplicate key": raw=b'{"x":1,"x":2}'; physical=sd0._sha(raw)
            elif variant=="self canonical mismatch": doc["decision_sha256"]="0"*64; raw=sd0._canon(doc); physical=sd0._sha(raw); canonical="0"*64
            elif variant=="external canonical mismatch": canonical="0"*64
            else:
                if variant=="wrong schema": doc["schema_version"]="wrong"
                elif variant=="wrong decision id": doc["decision_id"]="wrong"
                elif variant=="non-accept state": doc["decision_state"]="REJECT_R8_ROUTE_KEEP_PRODUCTION_SUSPENDED"
                elif variant=="missing activation id": doc["activation"].pop("unique_activation_id")
                elif variant=="malformed activation id": doc["activation"]["unique_activation_id"]="PITAR1-SD0-R8-ACT-not-hex"
                elif variant=="not-before in future":
                    future=datetime.now(timezone.utc)+timedelta(hours=2); doc["activation"]["not_before_utc"]=future.isoformat().replace("+00:00","Z"); doc["activation"]["expires_at_utc"]=(future+timedelta(hours=1)).isoformat().replace("+00:00","Z")
                elif variant=="expired completion":
                    past=datetime.now(timezone.utc)-timedelta(hours=2); doc["activation"]["not_before_utc"]=past.isoformat().replace("+00:00","Z"); doc["activation"]["expires_at_utc"]=(past+timedelta(hours=1)).isoformat().replace("+00:00","Z")
                else:
                    now=datetime.now(timezone.utc); doc["activation"]["not_before_utc"]=now.isoformat().replace("+00:00","Z"); doc["activation"]["expires_at_utc"]=(now+timedelta(seconds=86401)).isoformat().replace("+00:00","Z")
                doc["decision_sha256"]=sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion/v1",doc,"decision_sha256")
                raw=sd0._canon(doc); physical=sd0._sha(raw); canonical=doc["decision_sha256"]
            with self.subTest(variant=variant), self.assertRaises(sd0.SD0Error) as raised:
                sd0._mint_activation_capability(completion_raw_bytes=raw,expected_completion_physical_sha256=physical,expected_completion_canonical_sha256=canonical,exact_resolved_repository_root=root.resolve())
            if variant=="physical mismatch before JSON reliance": self.assertIn("physical",str(raised.exception))
            self.assertFalse(sd0._CAPABILITIES,variant)

    def test_r8_t46_completion_binding_and_permission_failures_do_not_mint(self) -> None:
        root=self._r8_gate_root(); raw,_,_=self._r8_completion(root); base=sd0._strict_json(raw)

        def paths(value,path=()):
            if isinstance(value,dict):
                for key,item in value.items():
                    if not path and key=="decision_sha256": continue
                    field_path=path+(key,); yield field_path; yield from paths(item,field_path)
            elif isinstance(value,list):
                for index,item in enumerate(value):
                    field_path=path+(index,); yield field_path; yield from paths(item,field_path)

        def parent_at(document,path):
            target=document
            for part in path[:-1]: target=target[part]
            return target

        def drift_value(value,path):
            if path[-1]=="reviewer": return ""
            if isinstance(value,bool): return not value
            if type(value) is int: return -1
            if isinstance(value,str): return "__DRIFT__"
            if isinstance(value,dict): return {}
            if isinstance(value,list): return []
            return None

        def candidate(path,probe):
            document=copy.deepcopy(base); parent=parent_at(document,path); key=path[-1]; value=parent[key]
            if probe=="missing": parent.pop(key) if isinstance(parent,dict) else parent.pop(key)
            elif probe=="extra":
                if isinstance(parent,dict): parent["__unexpected_completion_field__"]=True
                else: parent.append(copy.deepcopy(parent[0]))
            elif probe=="false": parent[key]=True if value is False else False
            else: parent[key]=drift_value(value,path)
            document["decision_sha256"]=sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion/v1",document,"decision_sha256")
            encoded=sd0._canon(document)
            return document,encoded

        field_paths=tuple(paths(base))
        self.assertGreater(len(field_paths),100)
        for path in field_paths:
            for probe in ("missing","extra","false","drift"):
                document,encoded=candidate(path,probe); label="/".join(map(str,path))
                try:
                    with self.subTest(group=path[0],field=label,probe=probe),self.assertRaises(sd0.SD0Error):
                        sd0._mint_activation_capability(
                            completion_raw_bytes=encoded,
                            expected_completion_physical_sha256=sd0._sha(encoded),
                            expected_completion_canonical_sha256=document["decision_sha256"],
                            exact_resolved_repository_root=root.resolve(),
                        )
                finally:
                    with sd0._CAPABILITY_LOCK: sd0._CAPABILITIES.clear()

        # Nonempty reviewers are still not independent when the identities match.
        duplicate=copy.deepcopy(base)
        duplicate["implementation_review"]["independent_reviews"][1]["reviewer"]=duplicate["implementation_review"]["independent_reviews"][0]["reviewer"]
        duplicate["decision_sha256"]=sd0._self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion/v1",duplicate,"decision_sha256")
        encoded=sd0._canon(duplicate)
        with self.subTest(group="implementation_review",field="reviewer",probe="duplicate"),self.assertRaises(sd0.SD0Error):
            sd0._mint_activation_capability(
                completion_raw_bytes=encoded,
                expected_completion_physical_sha256=sd0._sha(encoded),
                expected_completion_canonical_sha256=duplicate["decision_sha256"],
                exact_resolved_repository_root=root.resolve(),
            )
        self.assertFalse(sd0._CAPABILITIES)

    def test_r8_t47_capability_is_opaque_root_bound_and_single_session(self) -> None:
        root=self._r8_gate_root(); raw,physical,canonical=self._r8_completion(root)
        capability=sd0._mint_activation_capability(completion_raw_bytes=raw,expected_completion_physical_sha256=physical,expected_completion_canonical_sha256=canonical,exact_resolved_repository_root=root.resolve())
        carriers=(None,object(),"token",{},sd0._ActivationCapability())
        for carrier in carriers:
            with self.subTest(carrier=type(carrier).__name__), self.assertRaises(sd0.SD0Error):
                sd0._session_for(carrier,root,"MINTED","PREFLIGHT_STARTED")
        with self.assertRaises(TypeError): copy.copy(capability)
        with self.assertRaises(TypeError): copy.deepcopy(capability)
        with self.assertRaises(sd0.SD0Error): sd0._mint_activation_capability(completion_raw_bytes=raw,expected_completion_physical_sha256=physical,expected_completion_canonical_sha256=canonical,exact_resolved_repository_root=root.resolve())

        for variant in ("pid","root device","root inode","client source","test source","decision","completion physical","completion canonical","permission"):
            root=self._r8_gate_root(); cap=self._mint_r8(root); session=sd0._CAPABILITIES[id(cap)]
            if variant=="client source": (root/sd0.STATIC_PATHS[3]).write_bytes(b"drift")
            elif variant=="test source": (root/sd0.STATIC_PATHS[4]).write_bytes(b"drift")
            elif variant=="decision": (root/sd0.R8_DECISION_PATH).write_bytes(b"drift")
            else:
                with sd0._CAPABILITY_LOCK:
                    if variant=="pid": session.pid+=1
                    elif variant=="root device": session.root_device+=1
                    elif variant=="root inode": session.root_inode+=1
                    elif variant=="completion physical": session.completion_raw+=b" "
                    elif variant=="completion canonical": session.completion_canonical="0"*64
                    else: session.permissions["zip_get"]=True
            with self.subTest(binding=variant), self.assertRaises(sd0.SD0Error):
                sd0._session_for(cap,root,"MINTED","PREFLIGHT_STARTED")
            self.assertEqual("CONSUMED_OR_INVALIDATED",session.state)

        # Atomic concurrent transition: at most one caller can leave MINTED.
        root=self._r8_gate_root(); cap=self._mint_r8(root); outcomes=[]
        def race():
            try: sd0._session_for(cap,root,"MINTED","PREFLIGHT_STARTED"); outcomes.append("ok")
            except sd0.SD0Error: outcomes.append("closed")
        threads=[threading.Thread(target=race) for _ in range(2)]
        for item in threads: item.start()
        for item in threads: item.join()
        self.assertEqual(1,outcomes.count("ok")); self.assertEqual(1,outcomes.count("closed"))

        for variant,argv,error in (("argparse",[],SystemExit),("evidence read",["--tests-evidence","missing.json"],OSError)):
            root=self._r8_gate_root(); cap=self._mint_r8(root); session=sd0._CAPABILITIES[id(cap)]
            with patch.object(sd0,"ROOT",root),patch("sys.stderr",io.StringIO()),self.subTest(main=variant),self.assertRaises(error):
                sd0.main(argv,capability=cap)
            self.assertEqual("CONSUMED_OR_INVALIDATED",session.state)
            with self.assertRaises(sd0.SD0Error): sd0._session_for(cap,root,"MINTED","MINTED")

        # Repeated/reordered/failure/consumed lifecycle uses the real session path.
        self.tearDown(); self.setUp(); self.materialize_static_inputs(); self.materialize_empty_output_parents(); cap=self._mint_r8(self.root)
        with self.client_context(), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)

        self.tearDown(); self.setUp(); self.materialize_static_inputs(); self.materialize_empty_output_parents(); cap=self._mint_r8(self.root)
        with self.client_context(), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda _:self.fail("no opener"),capability=cap)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.persist_ready(self.root,ready,capability=cap)

        self.tearDown(); self.setUp(); self.materialize_static_inputs(); self.materialize_empty_output_parents(); cap=self._mint_r8(self.root)
        with self.client_context(), patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=0)):
            result=sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:self.fail("no tcp"),capability=cap)
        self.assertNotIsInstance(result,sd0.ReadyPreflight)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.preflight(self.root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)

        self.tearDown(); self.setUp(); ready=self.ready_preflight(); cap=self._fixture_capability; self.persist_ready(ready); calls,opener=self.good_opener()
        with self.client_context(): sd0.execute(self.root,ready=ready,opener=opener,capability=cap)
        with self.client_context(), self.assertRaises(sd0.SD0Error): sd0.execute(self.root,ready=ready,opener=lambda _:self.fail("consumed"),capability=cap)
        self.assertEqual(7,len(calls))

    def test_r8_t48_positive_in_memory_completion_mints_only_for_exact_temporary_root(self) -> None:
        workspace_paths=(sd0.PREFLIGHT_PATH,)+sd0.NETWORK_PATHS
        workspace_before=workspace_output_snapshot(workspace_paths)
        root=self._r8_runtime_root(); raw,physical,canonical=self._r8_completion(root)
        capability=sd0._mint_activation_capability(completion_raw_bytes=raw,expected_completion_physical_sha256=physical,expected_completion_canonical_sha256=canonical,exact_resolved_repository_root=root.resolve())
        calls=[]; responses=self.good_opener()[1]
        def opener(spec):
            calls.append(spec); return responses(spec)
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)),patch.object(sd0.socket,"create_connection",side_effect=AssertionError("real socket")),patch.object(sd0,"StdlibProxyOpener",side_effect=AssertionError("real proxy")):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=capability)
            self.assertIsInstance(ready,sd0.ReadyPreflight)
            sd0.persist_ready(root,ready,capability=capability)
            closure=sd0.execute(root,ready=ready,opener=opener,capability=capability)
        self.assertEqual([item[0] for item in sd0.EXACT],[item.request_id for item in calls])
        self.assertEqual(7,len(calls)); self.assertNotIn("SD0-008",[item.request_id for item in calls])
        ledger=[json.loads(line) for line in (root/sd0.NETWORK_PATHS[0]).read_text().splitlines()]
        self.assertEqual(7,len(ledger)); self.assertTrue(all(row["redirect_count"]==0 for row in ledger))
        self.assertEqual("WAIT_DATA_TERMS_D0_DENIED",closure["terminal_disposition"])
        self.assertEqual(workspace_before,workspace_output_snapshot(workspace_paths))

        # A first-request failure stops immediately and cannot retry.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); failed=[]
        def first_failure(spec):
            failed.append(spec.request_id); raise sd0.SD0Error("WAIT_DATA_NO_FALLBACK","offline failure")
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            sd0.persist_ready(root,ready,capability=cap)
            with self.assertRaises(sd0.SD0Error): sd0.execute(root,ready=ready,opener=first_failure,capability=cap)
        self.assertEqual(["SD0-001"],failed)
        failed_ledger=[json.loads(line) for line in (root/sd0.NETWORK_PATHS[0]).read_text().splitlines()]
        self.assertEqual(1,len(failed_ledger)); self.assertEqual(0,failed_ledger[0]["redirect_count"])

    def test_r8_t49_workspace_root_rejects_injected_callbacks_before_invocation(self) -> None:
        workspace_paths=(sd0.PREFLIGHT_PATH,)+sd0.NETWORK_PATHS
        workspace_before=workspace_output_snapshot(workspace_paths)
        source=(REPOSITORY/sd0.STATIC_PATHS[3]).read_text()
        for forbidden in ("os.environ","Keychain","latest-file","glob(","marker_path","resume_path","ACTIVE_G1"):
            with self.subTest(scan=forbidden): self.assertNotIn(forbidden,source)
        tree=ast.parse(source)
        definitions={node.name:node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        call_graph={}
        for name,node in definitions.items():
            calls=set()
            for child in ast.walk(node):
                if isinstance(child,ast.Call):
                    if isinstance(child.func,ast.Name): calls.add(child.func.id)
                    elif isinstance(child.func,ast.Attribute): calls.add(child.func.attr)
            call_graph[name]=calls
        reachable=set(("main","preflight","persist_ready","execute")); pending=list(reachable)
        while pending:
            for called in call_graph.get(pending.pop(),()):
                if called in definitions and called not in reachable: reachable.add(called); pending.append(called)
        forbidden_route_tokens=("adapter","replay","dataset","backtest","paper","testnet","deploy","trad","account","order","fund","market_row","zip_get","active_g1")
        self.assertEqual([],sorted(name for name in reachable if any(token in name.lower() for token in forbidden_route_tokens)))
        local_callables={name for name,value in vars(sd0).items() if callable(value) and getattr(value,"__module__",None)==sd0.__name__}
        self.assertEqual([],sorted(name for name in local_callables if any(token in name.lower() for token in forbidden_route_tokens)))
        self.assertEqual(["SD0Error"],sorted(name for name in reachable if "d0" in name.lower()))
        self.assertEqual(["SD0Error"],sorted(name for name in local_callables if "d0" in name.lower()))
        self.assertNotIn(("GET","https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-03.zip"),[(item[1],item[2]) for item in sd0.EXACT])
        self.assertTrue(all(method!="GET" or not url.endswith(".zip") for _,method,url,_,_ in sd0.EXACT))
        self.assertEqual(7,len(sd0.EXACT))
        for entry in (sd0.main,sd0.preflight,sd0.persist_ready,sd0.execute):
            self.assertIn("capability",inspect.signature(entry).parameters)

        # Production TCP callback is rejected before invocation.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); calls=[]
        with patch.object(sd0,"_INITIAL_ROOT",root.resolve()),self.assertRaises(sd0.SD0Error):
            sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append("tcp"),capability=cap)
        self.assertEqual([],calls); self.assertFalse(any((root/path).exists() for path in workspace_paths))

        # All four public entrypoints reject a capability at an alternate root.
        for entry in ("main","preflight","persist","execute"):
            root=self._r8_runtime_root(); cap=self._mint_r8(root); other=(root/f"alternate-{entry}"); other.mkdir(); calls=[]; forged=sd0.ReadyPreflight(b"{}","0"*64)
            with patch.object(sd0,"ROOT",other),self.subTest(alternate_root=entry),self.assertRaises(sd0.SD0Error):
                if entry=="main": sd0.main(["--tests-evidence","never-read.json"],capability=cap)
                elif entry=="preflight": sd0.preflight(other,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append("tcp"),capability=cap)
                elif entry=="persist": sd0.persist_ready(other,forged,capability=cap)
                else: sd0.execute(other,ready=forged,opener=lambda _spec:calls.append("opener"),capability=cap)
            self.assertEqual([],calls,entry); self.assertFalse(any((other/path).exists() for path in workspace_paths),entry)

        # Every session-bound authority/source/completion value is rechecked before TCP.
        preflight_swaps=("R7 completion","R8","client","test","completion snapshot","activation id","permission","expiry")
        for variant in preflight_swaps:
            root=self._r8_runtime_root(); cap=self._mint_r8(root); session=sd0._CAPABILITIES[id(cap)]; calls=[]
            if variant=="R7 completion": (root/sd0.R7_COMPLETION_PATH).write_bytes(b"drift")
            elif variant=="R8": (root/sd0.R8_DECISION_PATH).write_bytes(b"drift")
            elif variant=="client": (root/sd0.STATIC_PATHS[3]).write_bytes(b"drift")
            elif variant=="test": (root/sd0.STATIC_PATHS[4]).write_bytes(b"drift")
            else:
                with sd0._CAPABILITY_LOCK:
                    if variant=="completion snapshot": session.completion_raw+=b" "
                    elif variant=="activation id": session.activation_id="PITAR1-SD0-R8-ACT-"+"0"*32
                    elif variant=="permission": session.permissions["zip_get"]=True
                    else: session.monotonic_expiry=0.0
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)),self.subTest(stage="preflight",swap=variant),self.assertRaises(sd0.SD0Error):
                sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:calls.append("tcp"),capability=cap)
            self.assertEqual([],calls,variant); self.assertFalse(any((root/path).exists() for path in workspace_paths),variant)

        def mutate_binding(root,session,ready,variant):
            if variant=="R7 completion": (root/sd0.R7_COMPLETION_PATH).write_bytes(b"drift")
            elif variant=="R8": (root/sd0.R8_DECISION_PATH).write_bytes(b"drift")
            elif variant=="client": (root/sd0.STATIC_PATHS[3]).write_bytes(b"drift")
            elif variant=="test": (root/sd0.STATIC_PATHS[4]).write_bytes(b"drift")
            else:
                field=variant.removeprefix("READY record ")
                with sd0._CAPABILITY_LOCK:
                    if variant=="completion raw": session.completion_raw+=b" "
                    elif variant=="completion physical": session.completion_physical="0"*64
                    elif variant=="completion canonical": session.completion_canonical="0"*64
                    elif variant=="activation id": session.activation_id="PITAR1-SD0-R8-ACT-"+"0"*32
                    elif variant=="permission": session.permissions["zip_get"]=True
                    elif variant=="expiry": session.monotonic_expiry=0.0
                    else:
                        record=sd0._READY[ready.digest]
                        replacements={
                            "snapshot":record.snapshot+b" ",
                            "context":{},
                            "capability":sd0._ActivationCapability(),
                            "capability_id":record.capability_id+1,
                            "completion_physical":"0"*64,
                            "completion_canonical":"0"*64,
                            "activation_id":"PITAR1-SD0-R8-ACT-"+"0"*32,
                            "monotonic_deadline":record.monotonic_deadline+1.0,
                            "run_id":"sd0-wrong",
                            "ready":sd0.ReadyPreflight(record.snapshot,record.ready_digest),
                            "ready_digest":"0"*64,
                        }
                        sd0._READY[ready.digest]=replace(record,**{field:replacements[field]})

        record_fields=("snapshot","context","capability","capability_id","completion_physical","completion_canonical","activation_id","monotonic_deadline","run_id","ready","ready_digest")
        boundary_swaps=("R7 completion","R8","client","test","completion raw","completion physical","completion canonical","activation id","permission","expiry")+tuple(f"READY record {field}" for field in record_fields)

        # Full binding matrix at preflight -> persist: no READY document is created.
        for variant in boundary_swaps:
            root=self._r8_runtime_root(); cap=self._mint_r8(root)
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            session=sd0._CAPABILITIES[id(cap)]; mutate_binding(root,session,ready,variant)
            with self._r8_runtime_context(root),self.subTest(stage="preflight-to-persist",swap=variant),self.assertRaises(sd0.SD0Error):
                sd0.persist_ready(root,ready,capability=cap)
            self.assertEqual("CONSUMED_OR_INVALIDATED",session.state,variant)
            self.assertFalse((root/sd0.PREFLIGHT_PATH).exists(),variant); self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS),variant)

        # The same full matrix at persist -> execute fails before opener/ledgers.
        for variant in boundary_swaps:
            root=self._r8_runtime_root(); cap=self._mint_r8(root); calls=[]
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
                sd0.persist_ready(root,ready,capability=cap)
            session=sd0._CAPABILITIES[id(cap)]; mutate_binding(root,session,ready,variant)
            with self._r8_runtime_context(root),self.subTest(stage="persist-to-execute",swap=variant),self.assertRaises(sd0.SD0Error):
                sd0.execute(root,ready=ready,opener=lambda spec:calls.append(spec),capability=cap)
            self.assertEqual([],calls,variant); self.assertEqual("CONSUMED_OR_INVALIDATED",session.state,variant)
            self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS),variant)

        # A missing READY after the lifecycle transition consumes the session immediately.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); calls=[]
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            sd0.persist_ready(root,ready,capability=cap)
            with self.assertRaises(sd0.SD0Error): sd0.execute(root,ready=None,opener=lambda spec:calls.append(spec),capability=cap)
        session=sd0._CAPABILITIES[id(cap)]
        self.assertEqual([],calls); self.assertEqual("CONSUMED_OR_INVALIDATED",session.state)
        self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS))

        # Drift after the first ledger create cannot reach the second create.
        for variant in ("permission","expiry","R8"):
            root=self._r8_runtime_root(); cap=self._mint_r8(root); calls=[]; creates=[]
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
                sd0.persist_ready(root,ready,capability=cap)
            session=sd0._CAPABILITIES[id(cap)]; real_create=sd0.Budget.create
            def drift_after_first_create(budget,safe,rel,data,*,append=False,_variant=variant):
                fd=real_create(budget,safe,rel,data,append=append); creates.append(rel)
                if rel==sd0.NETWORK_PATHS[0]:
                    if _variant=="R8": (root/sd0.R8_DECISION_PATH).write_bytes(b"drift")
                    else:
                        with sd0._CAPABILITY_LOCK:
                            if _variant=="permission": session.permissions["zip_get"]=True
                            else: session.monotonic_expiry=0.0
                return fd
            with self._r8_runtime_context(root),patch.object(sd0.Budget,"create",new=drift_after_first_create),self.subTest(stage="between-ledger-creates",swap=variant),self.assertRaises(sd0.SD0Error):
                sd0.execute(root,ready=ready,opener=lambda spec:calls.append(spec),capability=cap)
            self.assertEqual([sd0.NETWORK_PATHS[0]],creates,variant); self.assertEqual([],calls,variant)
            self.assertTrue((root/sd0.NETWORK_PATHS[0]).exists(),variant)
            self.assertFalse((root/sd0.NETWORK_PATHS[1]).exists(),variant)
            self.assertEqual("CONSUMED_OR_INVALIDATED",session.state,variant)

        # Without drift, the same boundary creates both ledgers.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); responses=self.good_opener()[1]
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            sd0.persist_ready(root,ready,capability=cap)
            sd0.execute(root,ready=ready,opener=responses,capability=cap)
        self.assertTrue((root/sd0.NETWORK_PATHS[0]).is_file())
        self.assertTrue((root/sd0.NETWORK_PATHS[1]).is_file())

        def callback_drift(root,session,variant):
            with sd0._CAPABILITY_LOCK:
                if variant=="expiry": session.monotonic_expiry=0.0
                elif variant=="permission": session.permissions["zip_get"]=True
            if variant=="R8": (root/sd0.R8_DECISION_PATH).write_bytes(b"drift")
            elif variant=="client": (root/sd0.STATIC_PATHS[3]).write_bytes(b"drift")

        # TCP callback changes are detected after callback return and never issue READY.
        for variant in ("expiry","R8","client","permission"):
            root=self._r8_runtime_root(); cap=self._mint_r8(root); session=sd0._CAPABILITIES[id(cap)]; calls=[]; ready_before=set(sd0._READY)
            def drifting_tcp(*_args, _root=root, _session=session, _variant=variant):
                calls.append("tcp"); callback_drift(_root,_session,_variant); return True
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)),self.subTest(stage="tcp-return",swap=variant),self.assertRaises(sd0.SD0Error):
                sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=drifting_tcp,capability=cap)
            self.assertEqual(["tcp"],calls,variant); self.assertEqual(ready_before,set(sd0._READY),variant)
            self.assertEqual("CONSUMED_OR_INVALIDATED",session.state,variant)
            self.assertFalse(any((root/path).exists() for path in workspace_paths),variant)

        # Opener-internal drift on request 1 or 7 escapes response sealing.
        for request_id,expected_rows in (("SD0-001",0),("SD0-007",6)):
            for variant in ("expiry","R8","client","permission"):
                root=self._r8_runtime_root(); cap=self._mint_r8(root); responses=self.good_opener()[1]; calls=[]
                with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                    ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
                    sd0.persist_ready(root,ready,capability=cap)
                session=sd0._CAPABILITIES[id(cap)]
                def drifting_opener(spec,_target=request_id,_variant=variant,_root=root,_session=session):
                    calls.append(spec.request_id)
                    if spec.request_id==_target: callback_drift(_root,_session,_variant)
                    return responses(spec)
                with self._r8_runtime_context(root),self.subTest(stage="opener-return",request=request_id,swap=variant),self.assertRaises(sd0.SD0Error):
                    sd0.execute(root,ready=ready,opener=drifting_opener,capability=cap)
                request_rows=(root/sd0.NETWORK_PATHS[0]).read_text().splitlines()
                header_rows=(root/sd0.NETWORK_PATHS[1]).read_text().splitlines()
                self.assertEqual(expected_rows,len(request_rows),(request_id,variant)); self.assertEqual(expected_rows,len(header_rows),(request_id,variant))
                self.assertEqual(expected_rows+1,len(calls),(request_id,variant))
                expected_documents=set() if request_id=="SD0-001" else set(sd0.NETWORK_PATHS[2:5])
                self.assertEqual(expected_documents,{path for path in sd0.NETWORK_PATHS[2:5] if (root/path).exists()},(request_id,variant))
                self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS[5:]),(request_id,variant))
                self.assertEqual("CONSUMED_OR_INVALIDATED",session.state,(request_id,variant))

        # Drift first visible at the next pre-opener check is not sealed as a row.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); responses=self.good_opener()[1]; calls=[]
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            sd0.persist_ready(root,ready,capability=cap)
        session=sd0._CAPABILITIES[id(cap)]; real_stage=sd0._stage_revalidate; stage_calls=0
        def drift_at_next_pre_opener(*args,**kwargs):
            nonlocal stage_calls
            stage_calls+=1
            if stage_calls==7:
                with sd0._CAPABILITY_LOCK: session.permissions["zip_get"]=True
            return real_stage(*args,**kwargs)
        def counted_opener(spec):
            calls.append(spec.request_id); return responses(spec)
        with self._r8_runtime_context(root),patch.object(sd0,"_stage_revalidate",side_effect=drift_at_next_pre_opener),self.assertRaises(sd0.SD0Error):
            sd0.execute(root,ready=ready,opener=counted_opener,capability=cap)
        self.assertEqual(["SD0-001"],calls); self.assertEqual(1,len((root/sd0.NETWORK_PATHS[0]).read_text().splitlines()))
        self.assertEqual(1,len((root/sd0.NETWORK_PATHS[1]).read_text().splitlines()))
        self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS[2:]))

        # Final HEAD, closure, and inventory creates each have their own last check.
        for boundary_call,existing_finals in ((34,0),(35,1),(36,2)):
            root=self._r8_runtime_root(); cap=self._mint_r8(root); responses=self.good_opener()[1]
            with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
                ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
                sd0.persist_ready(root,ready,capability=cap)
            session=sd0._CAPABILITIES[id(cap)]; real_stage=sd0._stage_revalidate; stage_calls=0
            def drift_at_final_boundary(*args,_boundary=boundary_call,**kwargs):
                nonlocal stage_calls
                stage_calls+=1
                if stage_calls==_boundary:
                    with sd0._CAPABILITY_LOCK: session.permissions["zip_get"]=True
                return real_stage(*args,**kwargs)
            with self._r8_runtime_context(root),patch.object(sd0,"_stage_revalidate",side_effect=drift_at_final_boundary),self.subTest(final_boundary=boundary_call),self.assertRaises(sd0.SD0Error):
                sd0.execute(root,ready=ready,opener=responses,capability=cap)
            self.assertEqual(7,len((root/sd0.NETWORK_PATHS[0]).read_text().splitlines()))
            self.assertTrue(all((root/path).exists() for path in sd0.NETWORK_PATHS[2:5]))
            self.assertEqual(existing_finals,sum((root/path).exists() for path in sd0.NETWORK_PATHS[5:]),boundary_call)

        # Production opener is rejected before constructing any runtime output.
        root=self._r8_runtime_root(); cap=self._mint_r8(root); calls=[]
        with self._r8_runtime_context(root),patch.object(sd0.shutil,"disk_usage",return_value=SimpleNamespace(free=2**63)):
            ready=sd0.preflight(root,tests_evidence=TEST_EVIDENCE,tcp_probe=lambda *_:True,capability=cap)
            sd0.persist_ready(root,ready,capability=cap)
        with patch.object(sd0,"_INITIAL_ROOT",root.resolve()),self._r8_runtime_context(root),self.assertRaises(sd0.SD0Error):
            sd0.execute(root,ready=ready,opener=lambda spec:calls.append(spec),capability=cap)
        self.assertEqual([],calls); self.assertFalse(any((root/path).exists() for path in sd0.NETWORK_PATHS))
        self.assertEqual(workspace_before,workspace_output_snapshot(workspace_paths))


if __name__ == "__main__":
    unittest.main()
