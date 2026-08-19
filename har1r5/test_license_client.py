"""No-network HAR1R5 production-style tests; the socket trap precedes import."""
import copy, hashlib, importlib, io, json, os, socket, sys, tempfile, threading, time, unittest, urllib.error
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
with mock.patch.object(socket,"socket",side_effect=AssertionError("HAR1R5_SOCKET_ZERO")):
    lc=importlib.import_module("har1r5.license_client")

class Response:
 def __init__(self,status=200,url=lc.URL,content="text/plain",body=None,headers=None,close_error=None,chunks=None):
  self.status=status; self.url=url; self.body=_license() if body is None else body; self.headers={"Content-Type":content} if headers is None else headers; self.closed=False; self.close_error=close_error; self.offset=0; self.chunks=list(chunks) if chunks is not None else None
 def geturl(self):return self.url
 def read(self,n):
  if self.chunks is not None:return self.chunks.pop(0) if self.chunks else b""
  value=self.body[self.offset:self.offset+n]; self.offset+=len(value); return value
 def close(self):self.closed=True
class ClosingResponse(Response):
 def close(self): self.closed=True; raise OSError("close")
class HeaderList:
 def __init__(self,pairs):self.pairs=pairs
 def items(self):return list(self.pairs)
 def get_all(self,name):return [v for k,v in self.pairs if k.lower()==name.lower()]
def _license():return b"Binance\nCopyright 2026\nPermission granted license\nSubject to condition\nAS IS warranty\nliability\n"
class Guard:
 def __enter__(self):return self
 def __exit__(self,*x):return False
def _activation(now=None):
 now=time.time() if now is None else now
 d={"schema_version":"har1r5-raw-license-candidate-activation.v1","decision_id":"SOL_HAR1R5_RAW_LICENSE_CANDIDATE_ACTIVATION.v1","permission":"ONE_GET_LICENSE_RAW_CANDIDATE","issued_at_utc":lc._utc(now-1),"expires_at_utc":lc._utc(now+100),"bindings":lc._activation_bindings(),"canonical_self_digest":{"algorithm":"SHA-256_CANONICAL_JSON","digest_field":"activation_sha256","domain_prefix_utf8":"msta-hed/har1r5-raw-license-candidate-activation/v1"}}
 d["activation_sha256"]=hashlib.sha256(b"msta-hed/har1r5-raw-license-candidate-activation/v1\0"+lc._canon(d)).hexdigest(); return lc._canon(d)
def _cap():return lc.issue_activation_capability(_activation())
def _cap_for(root):
 raw=_activation(); cap=lc.issue_activation_capability(raw); lc._write_r4(root,lc.ACTIVATION_PATH,raw); return cap
def _run(response,root):
 cap=_cap_for(root)
 with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
  return lc._execute_with_transport(cap,lambda *a:response,root,monotonic=lambda:1.0,wall=time.time,deadline_factory=lambda _:Guard())
def _records(root):return [json.loads(line) for line in (root/lc.EVIDENCE_PATH).read_text().splitlines()]
def _rechain(root,records):
 previous="0"*64; lines=[]
 for record in records:
  record["previous_raw_line_sha256"]=previous; line=lc._canon(record); lines.append(line); previous=hashlib.sha256(line+b"\n").hexdigest()
 (root/lc.EVIDENCE_PATH).write_bytes(b"\n".join(lines)+b"\n")
def _live(root):
 q=_records(root); q=q[1]; return {k:q[k] for k in ("status_code","final_url","content_type","content_type_values","header_bytes","location","set_cookie","etag","last_modified","date","response_bytes","body_sha256","outcome","errors","transport_error")}

class Tests(unittest.TestCase):
 def test_static_r3_r4_full_replay_socket_zero(self):
  self.assertEqual(lc.validate_static_files()[1]["raw_path"],lc.RAW_PATH); self.assertTrue(lc.replay_predecessors())
 def test_activation_strict_private_single_use(self):
  raw=_activation(); cap=lc.issue_activation_capability(raw); self.assertIsInstance(cap,lc.LicenseCapability)
  with self.assertRaises(PermissionError):lc.issue_activation_capability(raw)
  bad=json.loads(raw); bad["permission"]="bad"
  with self.assertRaises(lc.ContractError):lc.issue_activation_capability(lc._canon(bad))
  with self.assertRaises(PermissionError):lc.LicenseCapability(None,"","",{},0,1)
 def test_forced_proxy_sets_proxy_and_no_redirect(self):
  class Request:
   def __init__(self):self.value=None
   def set_proxy(self,*x):self.value=x
  req=Request(); self.assertIsNone(lc.R4._ForcedHttpsProxyHandler().proxy_open(req,lc.PROXY,"https")); self.assertEqual(req.value,("127.0.0.1:7897","https")); self.assertIsNone(lc.R4._NoRedirect().redirect_request(None,None,None,None,None,None,None))
 def test_production_style_success_manifest_candidate(self):
  with tempfile.TemporaryDirectory() as td:
   manifest=_run(Response(),Path(td)); self.assertEqual(manifest["candidate_state"],"SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW"); self.assertFalse(manifest["terminal"]["legal_conclusion"]); self.assertTrue((Path(td)/lc.RAW_PATH).exists())
 def test_http403_and_redirect_are_raw_failure_terminal(self):
  for r in (Response(status=403),Response(url=lc.URL+"/elsewhere")):
   with self.subTest(status=r.status):
    with tempfile.TemporaryDirectory() as td:
     m=_run(r,Path(td)); self.assertEqual(m["request"]["outcome"],"FAILURE"); self.assertEqual(m["candidate_state"],"SEALED_NOT_LICENSE_WAIT_DATA"); self.assertTrue((Path(td)/lc.RAW_PATH).exists()); self.assertTrue(r.closed)
  with tempfile.TemporaryDirectory() as td:
   cap=_cap_for(Path(td)); error=urllib.error.HTTPError(lc.URL,403,"denied",{"Content-Type":"text/plain"},io.BytesIO(_license()))
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
    m=lc._execute_with_transport(cap,lambda *a: (_ for _ in ()).throw(error),Path(td),monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   self.assertEqual(m["request"]["status_code"],403); self.assertTrue((Path(td)/lc.RAW_PATH).exists())
 def test_transport_and_close_failures_no_raw_terminal(self):
  for transport in (lambda *a: (_ for _ in ()).throw(OSError("transport")),lambda *a: ClosingResponse()):
   with self.subTest(transport=transport):
    with tempfile.TemporaryDirectory() as td:
     cap=_cap_for(Path(td))
     with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
      m=lc._execute_with_transport(cap,transport,Path(td),monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
     self.assertEqual(m["request"]["outcome"],"FAILURE"); self.assertFalse((Path(td)/lc.RAW_PATH).exists())
 def test_header_body_cap_deadline_and_alarm(self):
  for huge in (Response(headers={"Content-Type":"text/plain","X":"x"*65537}),Response(body=b"x"*65537)):
   with tempfile.TemporaryDirectory() as td:
    cap=_cap_for(Path(td))
    with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
     m=lc._execute_with_transport(cap,lambda *a:huge,Path(td),monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
    self.assertEqual(m["request"]["outcome"],"FAILURE"); self.assertTrue(huge.closed)
  with self.assertRaises(OSError):
   cap=_cap()
   with mock.patch.object(lc.R3,"_require_production_alarm_available",side_effect=OSError("alarm")):lc._execute_with_transport(cap,lambda *a:Response(),ROOT)
 def test_main_thread_posix_itimer_guard(self):
  lc.R3._require_production_alarm_available()
  with lc.R3._posix_deadline(0.05):
   self.assertTrue(True)
 def test_absolute_twenty_second_deadline_is_failure(self):
  ticks=iter((0.0,20.0))
  with tempfile.TemporaryDirectory() as td:
   cap=_cap_for(Path(td))
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
    m=lc._execute_with_transport(cap,lambda *a:Response(),Path(td),monotonic=lambda:next(ticks),wall=time.time,deadline_factory=lambda _:Guard())
   self.assertEqual(m["request"]["outcome"],"FAILURE"); self.assertFalse((Path(td)/lc.RAW_PATH).exists())
 def test_bound_deadline_exception_is_terminal_without_raw(self):
  with tempfile.TemporaryDirectory() as td:
   cap=_cap_for(Path(td)); expired=lc.R3.R2_SAFETY._DeadlineExceeded()
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
    m=lc._execute_with_transport(cap,lambda *a: (_ for _ in ()).throw(expired),Path(td),monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   self.assertEqual(m["request"]["errors"],["REQUEST_DEADLINE_EXCEEDED"]); self.assertFalse((Path(td)/lc.RAW_PATH).exists())
 def test_replay_rechain_raw_swap_live_observation_and_manifest_requirements(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); m=_run(Response(),root); raw=(root/lc.EVIDENCE_PATH).read_bytes(); (root/lc.EVIDENCE_PATH).write_bytes(raw.replace(b'"REQUEST"',b'"REQUESTX"',1))
   with self.assertRaises(lc.EvidenceError):lc.replay_evidence(root,{})
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,None)
   self.assertEqual(m["schema_version"],"har1r5-license-manifest.v1")
 def test_invalid_utf8_bom_nul_are_raw_failure_terminals(self):
  for body in (b"\xff",b"\xef\xbb\xbf"+_license(),_license()+b"\0"):
   with self.subTest(body=body[:3]),tempfile.TemporaryDirectory() as td:
    root=Path(td); m=_run(Response(body=body),root)
    self.assertEqual(m["candidate_state"],"SEALED_NOT_LICENSE_WAIT_DATA"); self.assertEqual(m["request"]["outcome"],"FAILURE"); self.assertEqual((root/lc.RAW_PATH).read_bytes(),body)
 def test_short_chunk_exact_cap_cap_plus_one_and_duplicate_content_type(self):
  cases=((Response(chunks=[_license()[:9],_license()[9:31],_license()[31:],b""]),True), (Response(body=b"x"*65536),True), (Response(body=b"x"*65537),False), (Response(headers=HeaderList([("Content-Type","text/plain"),("Content-Type","text/plain")])),True))
  for response,raw_expected in cases:
   with self.subTest(raw=raw_expected),tempfile.TemporaryDirectory() as td:
    root=Path(td); m=_run(response,root); self.assertEqual((root/lc.RAW_PATH).exists(),raw_expected); self.assertTrue(response.closed)
    if isinstance(response.headers,HeaderList):self.assertEqual(m["request"]["errors"],["CONTENT_TYPE_CARDINALITY"]); self.assertIsNone(m["request"]["content_type"]); self.assertEqual(m["request"]["content_type_values"],["text/plain","text/plain"])
 def test_rechain_resign_rejects_exact_schema_and_fixed_relations(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); _run(Response(),root)
   mutations=(lambda r:r[1].__setitem__("extra",1),lambda r:r[1].pop("method"),lambda r:r[1].__setitem__("method","POST"),lambda r:r[1].__setitem__("requested_url","https://wrong"),lambda r:r[1].__setitem__("request_headers",{}),lambda r:r[1].__setitem__("status_code","200"),lambda r:r[1].__setitem__("received_at_utc","bad"),lambda r:r[2].__setitem__("legal_conclusion",True),lambda r:r[2].__setitem__("candidate_state","SEALED_NOT_LICENSE_WAIT_DATA"))
   for mutate in mutations:
    records=_records(root); mutate(records); _rechain(root,records)
    with self.assertRaises((lc.EvidenceError,lc.ContractError)):lc.replay_evidence(root,_live(root))
    _run_reset=root/lc.EVIDENCE_PATH
    # Restore an untampered, independently generated terminal for the next case.
    _run_reset.unlink(); (root/lc.MANIFEST_PATH).unlink(); (root/lc.RAW_PATH).unlink(); (root/lc.ACTIVATION_PATH).unlink(); _run(Response(),root)
 def test_activation_binding_and_post_issue_drift_are_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); _run(Response(),root); activation=json.loads((root/lc.ACTIVATION_PATH).read_bytes()); activation["bindings"]={"forged":True}; activation["activation_sha256"]=hashlib.sha256(b"msta-hed/har1r5-raw-license-candidate-activation/v1\0"+lc._canon({k:v for k,v in activation.items() if k!="activation_sha256"})).hexdigest(); (root/lc.ACTIVATION_PATH).write_bytes(lc._canon(activation))
   with self.assertRaises((lc.EvidenceError,lc.ContractError)):lc.replay_evidence(root,_live(root))
  cap=_cap()
  with mock.patch.object(lc,"validate_static_files"),mock.patch.object(lc,"replay_predecessors"),mock.patch.object(lc,"_activation_bindings",return_value={"drift":True}):
   with self.assertRaises(lc.ContractError):lc._pre_tcp(cap,ROOT)
 def test_full_activation_resign_is_rejected_against_current_bindings(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); manifest=_run(Response(),root); records=_records(root); activation=json.loads((root/lc.ACTIVATION_PATH).read_bytes()); activation["bindings"]={"forged":True}; unsigned={k:v for k,v in activation.items() if k!="activation_sha256"}; activation["activation_sha256"]=hashlib.sha256(b"msta-hed/har1r5-raw-license-candidate-activation/v1\0"+lc._canon(unsigned)).hexdigest(); raw=lc._canon(activation); (root/lc.ACTIVATION_PATH).write_bytes(raw)
   records[0]["activation_raw_physical_sha256"]=hashlib.sha256(raw).hexdigest(); records[0]["activation_sha256"]=activation["activation_sha256"]; records[0]["bindings"]=activation["bindings"]; _rechain(root,records); forged=lc._manifest(root,records,manifest["completed_at_utc"]); (root/lc.MANIFEST_PATH).write_bytes(lc._canon(forged))
   with self.assertRaises((lc.EvidenceError,lc.ContractError)):lc.validate_manifest(root,_live(root))
 def test_live_receipt_rejects_plain_mapping_and_global_authority_drift(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); _run(Response(),root); receipt=_live(root)
   with self.assertRaises(lc.EvidenceError):lc.replay_evidence(root,{})
   with self.assertRaises(PermissionError):lc.LiveObservationCapability(None,{})
   with mock.patch.object(lc,"validate_static_files",side_effect=lc.ContractError("global drift")):
    with self.assertRaises(lc.ContractError):lc.replay_evidence(root,receipt)
 def test_post_persist_run_receipt_rejects_resigned_403_mutation(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); cap=_cap_for(root); original=lc.validate_manifest; captured=[]
   def intercept(bound_root,receipt):
    captured.append(receipt); records=_records(bound_root); records[1]["status_code"]=200; records[1]["errors"]=[]; records[1]["outcome"]="SUCCESS"; records[2]["candidate_state"]="SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW"; _rechain(bound_root,records); previous=json.loads((bound_root/lc.MANIFEST_PATH).read_bytes()); (bound_root/lc.MANIFEST_PATH).write_bytes(lc._canon(lc._manifest(bound_root,records,previous["completed_at_utc"]))); return original(bound_root,receipt)
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"),mock.patch.object(lc,"validate_manifest",side_effect=intercept):
    with self.assertRaises(lc.EvidenceError):lc._execute_with_transport(cap,lambda *a:Response(status=403),root,monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   self.assertEqual(len(captured),1); self.assertIsInstance(captured[0],lc.RunReceipt)
   with self.assertRaises(PermissionError):copy.copy(captured[0])
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,None)
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,{})
   forged=object.__new__(lc.RunReceipt)
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,forged)
   captured[0]._pid=-1
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,captured[0])
 def test_403_rechain_cannot_self_issue_execution_authority(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); cap=_cap_for(root)
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"):
    lc._execute_with_transport(cap,lambda *a:Response(status=403),root,monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   self.assertTrue(cap._used)
   records=_records(root); records[1]["status_code"]=200; records[1]["errors"]=[]; records[1]["outcome"]="SUCCESS"; records[2]["candidate_state"]="SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW"; _rechain(root,records)
   previous=json.loads((root/lc.MANIFEST_PATH).read_bytes()); (root/lc.MANIFEST_PATH).write_bytes(lc._canon(lc._manifest(root,records,previous["completed_at_utc"])))
   with self.assertRaises(lc.EvidenceError):lc._issue_live_observation(_live(root))
   with self.assertRaises(lc.EvidenceError):lc._issue_run_receipt(root,cap,{})
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,lc.RunReceipt(object()))
 def test_captured_receipt_output_tamper_consumes_before_retry(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); cap=_cap_for(root); captured=[]
   def hold(bound_root,receipt):captured.append(receipt); return {"held":True}
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"),mock.patch.object(lc,"validate_manifest",side_effect=hold):
    self.assertEqual(lc._execute_with_transport(cap,lambda *a:Response(),root,monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard()),{"held":True})
   raw=(root/lc.EVIDENCE_PATH).read_bytes(); (root/lc.EVIDENCE_PATH).write_bytes(raw.replace(b'"REQUEST"',b'"REQUESTX"',1))
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,captured[0])
   with self.assertRaises(lc.EvidenceError):lc.validate_manifest(root,captured[0])
 def test_same_captured_receipt_validates_in_exactly_one_thread(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); cap=_cap_for(root); captured=[]
   def hold(bound_root,receipt):captured.append(receipt); return {"held":True}
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"),mock.patch.object(lc,"validate_manifest",side_effect=hold):
    lc._execute_with_transport(cap,lambda *a:Response(),root,monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   start=threading.Barrier(8); success=[]; rejected=[]
   def validate():
    start.wait()
    try:success.append(lc.validate_manifest(root,captured[0]))
    except lc.EvidenceError:rejected.append(True)
   threads=[threading.Thread(target=validate) for _ in range(8)]; [x.start() for x in threads]; [x.join() for x in threads]
   self.assertEqual((len(success),len(rejected)),(1,7))
 def test_successful_run_receipt_is_consumed_and_not_returned(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); cap=_cap_for(root); original=lc.validate_manifest; captured=[]
   def intercept(bound_root,receipt):captured.append(receipt); return original(bound_root,receipt)
   with mock.patch.object(lc.R3,"_require_production_alarm_available"),mock.patch.object(lc,"_pre_tcp"),mock.patch.object(lc,"validate_manifest",side_effect=intercept):
    result=lc._execute_with_transport(cap,lambda *a:Response(),root,monotonic=lambda:1,wall=time.time,deadline_factory=lambda _:Guard())
   self.assertIsInstance(result,dict); self.assertNotIsInstance(result,lc.RunReceipt); self.assertEqual(len(captured),1)
   with self.assertRaises(lc.EvidenceError):original(root,captured[0])
 def test_activation_issue_and_consume_are_thread_atomic(self):
  class SlowSet(set):
   def __contains__(self,item):
    time.sleep(0.002); return super().__contains__(item)
  raw=_activation(); start=threading.Barrier(8); issued=[]; failures=[]
  def issue():
   start.wait()
   try:issued.append(lc.issue_activation_capability(raw))
   except PermissionError:failures.append(True)
  with mock.patch.object(lc,"_issued",SlowSet()):
   threads=[threading.Thread(target=issue) for _ in range(8)]
   [x.start() for x in threads]; [x.join() for x in threads]
  self.assertEqual((len(issued),len(failures)),(1,7)); cap=issued[0]; start=threading.Barrier(8); consumed=[]
  def consume():
   start.wait()
   try:lc._consume(cap); consumed.append(True)
   except PermissionError:pass
  threads=[threading.Thread(target=consume) for _ in range(8)]; [x.start() for x in threads]; [x.join() for x in threads]
  self.assertEqual(len(consumed),1)
 def test_bool_int_full_resign_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); manifest=_run(Response(),root); records=_records(root); records[0]["terminal"]=0; records[1]["sequence"]=True; records[1]["request_attempted"]=1; records[2]["terminal"]=1; records[2]["legal_conclusion"]=0; records[2]["archive_scope_automatic_judgment"]=0; _rechain(root,records); forged=lc._manifest(root,records,manifest["completed_at_utc"]); (root/lc.MANIFEST_PATH).write_bytes(lc._canon(forged))
   with self.assertRaises((lc.EvidenceError,lc.ContractError)):lc.validate_manifest(root,_live(root))
 def test_nofollow_create_once_and_future_outputs_absent(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); lc._write_r4(root,"safe/file",b"x")
   with self.assertRaises(Exception):lc._write_r4(root,"safe/file",b"y")
   (root/"link").symlink_to(root/"safe",target_is_directory=True)
   with self.assertRaises(Exception):lc._write_r4(root,"link/no",b"x")
  for p in (lc.ACTIVATION_PATH,lc.EVIDENCE_PATH,lc.RAW_PATH,lc.MANIFEST_PATH):self.assertFalse((ROOT/p).exists())
 def test_extract_is_auditable_not_legal(self):
  candidate,state=lc._extract(_license()); self.assertEqual(state,"SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW"); self.assertTrue(all(candidate[x]["line_numbers"] for x in ("identity_candidate","copyright","grant","conditions","warranty","liability"))); self.assertIn("git_blob_sha1",candidate)

if __name__=="__main__":unittest.main()
