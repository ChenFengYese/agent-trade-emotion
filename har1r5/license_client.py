"""Dormant HAR1R5 raw-LICENSE evidence client; importing it is side-effect free."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import MappingProxyType, ModuleType

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "har1r5-raw-license-candidate-v1"
ROUTE_PATH = "config/sol_decision.har1r5-raw-license-candidate-route.v1.json"
PLAN_PATH, CONTRACT_PATH = "har1r5/license_request_plan.json", "har1r5/license_contract.json"
ACTIVATION_PATH, EVIDENCE_PATH = "config/sol_activation.har1r5-raw-license-candidate.v1.json", "har1r5/evidence/requests.jsonl"
RAW_PATH, MANIFEST_PATH = "har1r5/evidence/raw/binance-public-data-LICENSE.raw", "har1r5/evidence/manifest.json"
URL, PROXY = "https://raw.githubusercontent.com/binance/binance-public-data/master/LICENSE", "http://127.0.0.1:7897"
HEADERS = {"Accept": "text/plain", "Accept-Encoding": "identity", "Connection": "close", "User-Agent": "agent-trade-emotion-har1r5-license/1.0"}
ROUTE_PHYSICAL, ROUTE_CANONICAL = "139131d3f0d06361f1acb6242d197ae07427afc1422bf88f446978ec1f28f00c", "9b82cc08e31bdfa36c3d921405473c82deb37d1bc1cf0adfb42a53635f37740e"
PLAN_PHYSICAL, PLAN_CANONICAL = "768a70935d288d2242bcf1f43c5bba8f925f442aa570caea141a90cfad8ba67c", "ab1a7fd2d75448ee91d265e87f3a885838f8460ad92f202115393a3f21a31747"
CONTRACT_PHYSICAL, CONTRACT_CANONICAL = "3d68346ad50f6fbabf3bd2913ac205df7931c71535e924a091a4b6e70455cf6d", "f0f445c6db6fadfe98733a36e503ca05f0e7346945cacdc8537e46b14f354d45"
R4_CLIENT_PHYSICAL = "5ab89f70372194840db9b13b4a71be9f662d5801e5aedd89eaebdd4e1cf33989"
PREDECESSORS = {
 "config/sol_decision.har1r3-dual-lane-successor-route.v1.json":"6b23ca9248233929023b29c606466af7063929e23fe70e89d01e0f1b2fca8c8d", "har1r3/technical_evidence.jsonl":"37ee748b04a412df58815da7421e51193878d3deb3ba3b8d02b0f6544d1c944f", "har1r3/terms_evidence/manifest.json":"43416222cd7188d7012740836ef2ac6d3029d19b461ea873abc4391f7546e0c2", "config/sol_activation.har1r4-source-terms-raw.v1.json":"bed93a1f5fc1f8dc338e58b8551ecb2a31414b3afcd0093d925f144daaee5d4f", "har1r4/source_terms_client.py":R4_CLIENT_PHYSICAL, "har1r4/evidence/requests.jsonl":"f34d80c6fb7be98e596ff61ba03ebd596d7306249828efdc87a7485335df3c52", "har1r4/evidence/manifest.json":"a6628b7d10141bb4107ba2b17c8918b0854ee2a02fc948af480ad470bf507ade", "config/har1_btcusdt_dataset_plan.v1.json":"e5b41825273e32fc67fa739cba6d56370869ecab52339affe14ee773ae281bd0"}

class ContractError(ValueError): pass
class ProtocolViolation(RuntimeError): pass
class EvidenceError(RuntimeError): pass
def _pairs(pairs):
 d={}
 for k,v in pairs:
  if k in d: raise ContractError("duplicate JSON key")
  d[k]=v
 return d
def _constant(v): raise ContractError("non-finite JSON")
def _canon(v): return json.dumps(v,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()
def _sha(v): return hashlib.sha256(v).hexdigest()
def _strict(raw):
 if type(raw) is not bytes or raw.startswith(b"\xef\xbb\xbf"): raise ContractError("strict bytes")
 try: v=json.loads(raw.decode("utf-8","strict"),object_pairs_hook=_pairs,parse_constant=_constant)
 except Exception as e: raise ContractError("strict JSON") from e
 if type(v) is not dict: raise ContractError("JSON object")
 return v
def _digest(d,field,domain):
 u=dict(d); claimed=u.pop(field,None); actual=_sha(domain.encode()+b"\0"+_canon(u))
 if type(claimed) is not str or claimed!=actual: raise ContractError("canonical digest")
 return actual
def _parts(p):
 x=Path(p)
 if x.is_absolute() or not x.parts or any(a in ("",".","..") for a in x.parts): raise ContractError("unsafe path")
 return x.parts
def _parent(root,relative,create=False):
 flags=os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0); fd=os.open(str(root),flags)
 try:
  for part in _parts(relative)[:-1]:
   try: child=os.open(part,flags,dir_fd=fd)
   except FileNotFoundError:
    if not create: raise
    os.mkdir(part,0o700,dir_fd=fd); os.fsync(fd); child=os.open(part,flags,dir_fd=fd)
   os.close(fd); fd=child
  return fd,_parts(relative)[-1]
 except Exception: os.close(fd); raise
def _read(root,relative):
 parent=fd=None
 try:
  parent,name=_parent(Path(root),relative); fd=os.open(name,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0),dir_fd=parent)
  if not stat.S_ISREG(os.fstat(fd).st_mode): raise ContractError("nonregular")
  chunks=[]
  while True:
   b=os.read(fd,65536)
   if not b:return b"".join(chunks)
   chunks.append(b)
 except OSError as e: raise ContractError("nofollow read") from e
 finally:
  if fd is not None: os.close(fd)
  if parent is not None: os.close(parent)
def _exists(root,p):
 parent=None
 try: parent,name=_parent(root,p); os.stat(name,dir_fd=parent,follow_symlinks=False); return True
 except FileNotFoundError:return False
 finally:
  if parent is not None:os.close(parent)
def _exact(a,b):
 if type(a) is not type(b):return False
 if type(b) is dict:return set(a)==set(b) and all(_exact(a[k],v) for k,v in b.items())
 if type(b) is list:return len(a)==len(b) and all(_exact(x,y) for x,y in zip(a,b))
 return a==b
def _utc(epoch=None): return dt.datetime.fromtimestamp(time.time() if epoch is None else epoch,dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def _parse_utc(s):
 if type(s) is not str or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z",s) is None: raise EvidenceError("canonical UTC")
 return dt.datetime.fromisoformat(s[:-1]+"+00:00").timestamp()

# R4 is physically pinned before its audited primitives are executed.  We reuse
# its dirfd writer, forced HTTPS proxy, redirect denial, POSIX alarm and bound
# R3 replay helpers; no network or output occurs while loading this module.
_r4_raw=_read(ROOT,"har1r4/source_terms_client.py")
if _sha(_r4_raw)!=R4_CLIENT_PHYSICAL: raise ImportError("final R4 client drift")
R4=ModuleType("_har1r5_final_r4"); R4.__file__=str(ROOT/"har1r4/source_terms_client.py")
exec(compile(_r4_raw,R4.__file__,"exec"),R4.__dict__)
R3=R4.R3_SAFETY

def validate_static_files(root=ROOT):
 files=((ROUTE_PATH,ROUTE_PHYSICAL,"decision_sha256","msta-hed/sol-har1r5-raw-license-candidate-route/v1",ROUTE_CANONICAL),(PLAN_PATH,PLAN_PHYSICAL,"request_plan_sha256","msta-hed/har1r5-license-request-plan/v1",PLAN_CANONICAL),(CONTRACT_PATH,CONTRACT_PHYSICAL,"license_contract_sha256","msta-hed/har1r5-license-contract/v1",CONTRACT_CANONICAL))
 docs=[]
 for p,h,f,domain,c in files:
  raw=_read(root,p)
  if _sha(raw)!=h:raise ContractError("physical drift: "+p)
  doc=_strict(raw)
  if _digest(doc,f,domain)!=c:raise ContractError("canonical drift: "+p)
  docs.append(doc)
 route,plan,contract=docs
 transport={"proxy":PROXY,"concurrency":1,"redirects":0,"retries":0,"cookies":False,"authentication":False,"api_key":False,"proxy_bypass":False,"tls_default_verification":True,"per_request_deadline_seconds":20,"total_deadline_seconds":20,"header_cap_bytes":65536,"body_cap_bytes":65536}
 req={"sequence":1,"method":"GET","url":URL,"headers":HEADERS}
 if route.get("decision_id")!="SOL_HAR1R5_RAW_LICENSE_CANDIDATE.v1" or not _exact(plan.get("transport"),transport) or not _exact(plan.get("request"),req):raise ContractError("static identity")
 if (plan.get("route_physical_sha256"),plan.get("route_canonical_sha256"),contract.get("route_physical_sha256"),contract.get("route_canonical_sha256"),contract.get("request_plan_physical_sha256"),contract.get("request_plan_canonical_sha256"))!=(ROUTE_PHYSICAL,ROUTE_CANONICAL,ROUTE_PHYSICAL,ROUTE_CANONICAL,PLAN_PHYSICAL,PLAN_CANONICAL):raise ContractError("cross binding")
 return route,plan,contract

def replay_predecessors(root=ROOT):
 root=Path(root); raw={p:_read(root,p) for p in PREDECESSORS}
 for p,h in PREDECESSORS.items():
  if _sha(raw[p])!=h:raise ContractError("predecessor physical: "+p)
 r3route=_strict(raw["config/sol_decision.har1r3-dual-lane-successor-route.v1.json"]); r4activation=_strict(raw["config/sol_activation.har1r4-source-terms-raw.v1.json"]); data=_strict(raw["config/har1_btcusdt_dataset_plan.v1.json"])
 if _digest(r3route,"decision_sha256","msta-hed/sol-har1r3-dual-lane-successor-route/v1")!="a21411873c7a793dc9d51983c4717ac3afad422bfe0d4f744679e9a51673b604":raise ContractError("R3 route canonical")
 if _digest(r4activation,"activation_sha256","msta-hed/har1r4-source-terms-raw-activation/v1")!="ec8a94c3b1aa6697c79a86e0613ae36c2a4d96e8523d82707666052b480e5db4":raise ContractError("R4 activation canonical")
 if _digest(data,"plan_sha256","msta-hed/har1-btcusdt-dataset-plan/v1")!="39853c9f92171bbcd851184842654829e1a1a1aa6522ccfa1d6ee8a3d91377e2" or data.get("status")!="PLAN_ONLY_NO_DOWNLOAD_NO_READ_NO_SCORE" or data.get("user_scope",{}).get("actor")!="NATURAL_PERSON":raise ContractError("data plan")
 # R4's own checked-in readback is reused to validate final client semantics.
 try: R4.validate_static_files(root); R4.replay_r3_sealed_inputs(root)
 except Exception as e: raise ContractError("R3/R4 audited replay") from e
 r4lines=[_strict(x) for x in raw["har1r4/evidence/requests.jsonl"].splitlines()]
 manifest=_strict(raw["har1r4/evidence/manifest.json"])
 if len(r4lines)!=6 or [x.get("status_code") for x in r4lines[1:5]]!=[403,403,403,202] or r4lines[-1].get("outcome")!="FAILURE" or r4lines[-1].get("repository_state")!="WAIT_DATA_SOURCE_CONTRACT_MISMATCH" or r4lines[-1].get("terms_state")!="WAIT_DATA_TERMS_D0_DENIED" or manifest.get("aggregate_outcome")!="FAILURE" or manifest.get("legal_conclusion") is not False:raise ContractError("R4 sealed outcome")
 return True

def _activation_bindings():
 route,plan,contract=validate_static_files(ROOT); data=_strict(_read(ROOT,"config/har1_btcusdt_dataset_plan.v1.json"))
 return {"route":{"physical":ROUTE_PHYSICAL,"canonical":ROUTE_CANONICAL},"plan":{"physical":PLAN_PHYSICAL,"canonical":PLAN_CANONICAL,"request":plan["request"],"transport":plan["transport"]},"contract":{"physical":CONTRACT_PHYSICAL,"canonical":CONTRACT_CANONICAL},"outputs":{"activation":ACTIVATION_PATH,"evidence":EVIDENCE_PATH,"raw":RAW_PATH,"manifest":MANIFEST_PATH},"user_scope":data["user_scope"],"data_plan":{"physical":PREDECESSORS["config/har1_btcusdt_dataset_plan.v1.json"],"canonical":"39853c9f92171bbcd851184842654829e1a1a1aa6522ccfa1d6ee8a3d91377e2"},"r3_r4":{p:{"physical":h} for p,h in PREDECESSORS.items() if "dataset" not in p},"client_physical":_sha(_read(ROOT,"har1r5/license_client.py")),"test_physical":_sha(_read(ROOT,"har1r5/test_license_client.py"))}

_issuer=object(); _issued=set(); _registry={}; _registry_lock=threading.Lock()
# A run receipt is admitted only by the closure in _execute_with_transport.
# The registry is deliberately process-local: this protects against ordinary
# module callers, not an attacker able to alter arbitrary process memory.
_live_issuer=object(); _live_registry={}; _run_registry={}; _run_registry_lock=threading.Lock()
class LicenseCapability:
 __slots__=("_used","_pid","_issued_at","_expires","_raw","_canonical","_bindings","_lock")
 def __init__(self,token,raw,canonical,bindings,issued,expires):
  if token is not _issuer:raise PermissionError("private issuer")
  self._used=False; self._pid=os.getpid(); self._issued_at=issued; self._expires=expires; self._raw=raw; self._canonical=canonical; self._bindings=MappingProxyType(json.loads(_canon(bindings).decode("utf-8"))); self._lock=threading.Lock()
 def __copy__(self):raise PermissionError("opaque")
 __deepcopy__=__reduce__=__copy__
class LiveObservationCapability:
 __slots__=("_pid","_raw")
 def __init__(self,token,values):
  if token is not _live_issuer:raise PermissionError("private live observation issuer")
  self._pid=os.getpid(); self._raw=_canon(values)
 def __copy__(self):raise PermissionError("opaque live observation")
 __deepcopy__=__reduce__=__copy__
def _issue_live_observation(values):
 # Retained only so an old caller fails closed rather than gaining authority.
 raise EvidenceError("live observations are execution scoped")
def _live_values(receipt):
 if type(receipt) is not LiveObservationCapability or receipt._pid!=os.getpid() or _live_registry.get(id(receipt)) is not receipt:raise EvidenceError("unissued live observation")
 return _strict(receipt._raw)
class RunReceipt:
 __slots__=("_pid","_used","_lock","_nonce")
 def __init__(self,nonce):
  self._pid=os.getpid(); self._used=False; self._lock=threading.Lock(); self._nonce=nonce
 def __copy__(self):raise PermissionError("opaque run receipt")
 __deepcopy__=__reduce__=__copy__
def _issue_run_receipt(root,cap,live):
 # Retained only so an old caller fails closed rather than gaining authority.
 raise EvidenceError("run receipts are execution scoped")
def _bound_outputs(root,state):
 info=os.stat(root)
 if (info.st_dev,info.st_ino)!=(state["root_dev"],state["root_ino"]) or _sha(_read(root,EVIDENCE_PATH))!=state["evidence_physical"] or _sha(_read(root,MANIFEST_PATH))!=state["manifest_physical"] or _exists(root,RAW_PATH)!=state["raw_exists"] or (state["raw_exists"] and _sha(_read(root,RAW_PATH))!=state["raw_physical"]):raise EvidenceError("run receipt output binding")
def _claim_run_receipt(root,receipt):
 try: valid=type(receipt) is RunReceipt and receipt._pid==os.getpid()
 except AttributeError: valid=False
 if not valid:raise EvidenceError("unissued run receipt")
 with _run_registry_lock:
  state=_run_registry.get(id(receipt))
  if type(state) is not dict or state.get("phase")!="SEALED" or state.get("receipt") is not receipt or state.get("nonce") is not receipt._nonce:raise EvidenceError("unissued run receipt")
 with receipt._lock:
   if receipt._used:raise EvidenceError("consumed run receipt")
   # Consume before any replay.  Therefore exactly one validator owns this
   # receipt, and a failed validation cannot be retried after re-signing.
   receipt._used=True; state["phase"]="CLAIMED"; _run_registry.pop(id(receipt),None)
 if state.get("cap") is None or id(state["cap"])!=state["cap_id"] or not state["cap"]._used or type(state.get("observation")) is not dict or state.get("observe_identity") is None or state.get("observation_identity")!=id(state["observation"]) or _canon(_live(state["observation"]))!=state["live_raw"]:raise EvidenceError("run receipt execution binding")
 _bound_outputs(root,state)
 return state
def issue_activation_capability(raw,now=None):
 d=_strict(raw); required={"schema_version","decision_id","permission","issued_at_utc","expires_at_utc","bindings","canonical_self_digest","activation_sha256"}
 if set(d)!=required or (d.get("schema_version"),d.get("decision_id"),d.get("permission"))!=("har1r5-raw-license-candidate-activation.v1","SOL_HAR1R5_RAW_LICENSE_CANDIDATE_ACTIVATION.v1","ONE_GET_LICENSE_RAW_CANDIDATE"):raise ContractError("activation schema")
 if not _exact(d["canonical_self_digest"],{"algorithm":"SHA-256_CANONICAL_JSON","digest_field":"activation_sha256","domain_prefix_utf8":"msta-hed/har1r5-raw-license-candidate-activation/v1"}):raise ContractError("activation metadata")
 canonical=_digest(d,"activation_sha256","msta-hed/har1r5-raw-license-candidate-activation/v1"); issued,expires=_parse_utc(d["issued_at_utc"]),_parse_utc(d["expires_at_utc"]); current=time.time() if now is None else now
 if not 0<expires-issued<=900 or not issued<=current<=expires or not _exact(d["bindings"],_activation_bindings()):raise ContractError("activation binding")
 with _registry_lock:
  if canonical in _issued:raise PermissionError("single use activation")
  cap=LicenseCapability(_issuer,_sha(raw),canonical,dict(d["bindings"]),issued,expires); _issued.add(canonical); _registry[id(cap)]=cap
 return cap
def _consume(cap):
 if type(cap) is not LicenseCapability or cap._pid!=os.getpid():raise PermissionError("capability")
 with _registry_lock:
  if _registry.get(id(cap)) is not cap:raise PermissionError("capability")
 with cap._lock:
  if cap._used or not cap._issued_at<=time.time()<=cap._expires:raise PermissionError("capability")
  cap._used=True
def _pre_tcp(cap,root):
 validate_static_files(root); replay_predecessors(root)
 raw=_read(root,ACTIVATION_PATH); d=_strict(raw)
 if not _exact(dict(cap._bindings),_activation_bindings()) or _sha(raw)!=cap._raw or _digest(d,"activation_sha256","msta-hed/har1r5-raw-license-candidate-activation/v1")!=cap._canonical or not _exact(d.get("bindings"),dict(cap._bindings)):raise ContractError("activation raw binding")
 for p in (EVIDENCE_PATH,RAW_PATH,MANIFEST_PATH):
  if _exists(root,p):raise ContractError("FAIL_CLOSED_NO_OVERWRITE")

def _headers(response):
 h=getattr(response,"headers",None)
 if h is None:raise ProtocolViolation("headers")
 pairs=list(h.items());
 if any(type(k) is not str or type(v) is not str for k,v in pairs):raise ProtocolViolation("header types")
 size=sum(len(k.encode("utf-8"))+2+len(v.encode("utf-8"))+2 for k,v in pairs)
 if size>65536:raise ProtocolViolation("HALT_RESOURCE_CAP_HEADER")
 def allv(name):
  g=getattr(h,"get_all",None); vals=(g(name) or []) if g else [v for k,v in pairs if k.lower()==name.lower()]
  if any(type(v) is not str for v in vals):raise ProtocolViolation("header values")
  return vals
 return pairs,size,allv("Location"),allv("Set-Cookie"),allv("ETag"),allv("Last-Modified"),allv("Date"),allv("Content-Type")
def _extract(raw):
 text=raw.decode("utf-8","strict"); lines=text.splitlines(); pats={"identity_candidate":r"(?:binance|author|licensor)","copyright":r"copyright","grant":r"(?:permission|granted|license)","conditions":r"(?:condition|subject to|provided that)","warranty":r"(?:warranty|as is)","liability":r"liabilit"}; out={}
 for name,p in pats.items():out[name]={"line_numbers":[i+1 for i,x in enumerate(lines) if re.search(p,x,re.I)],"label":name}
 out["raw_sha256"],out["git_blob_sha1"],out["bytes"]=_sha(raw),hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest(),len(raw)
 complete=all(out[n]["line_numbers"] for n in pats)
 return out,"SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW" if complete else "SEALED_NOT_LICENSE_WAIT_DATA"
def _empty_candidate(raw):
 return {"identity_candidate":{"line_numbers":[],"label":"identity_candidate"},"copyright":{"line_numbers":[],"label":"copyright"},"grant":{"line_numbers":[],"label":"grant"},"conditions":{"line_numbers":[],"label":"conditions"},"warranty":{"line_numbers":[],"label":"warranty"},"liability":{"line_numbers":[],"label":"liability"},"raw_sha256":_sha(raw) if raw is not None else None,"git_blob_sha1":hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest() if raw is not None else None,"bytes":len(raw) if raw is not None else 0}
def _safe_extract(raw):
 try:return _extract(raw)
 except UnicodeDecodeError:return _empty_candidate(raw),"SEALED_NOT_LICENSE_WAIT_DATA"
def _write_r4(root,path,raw):R4._ExclusiveFile(root,path).write_and_seal(raw)
def _line_records(cap,obs,candidate,now):
 activation={"schema_version":"har1r5-license-evidence.v1","record_type":"ACTIVATION","terminal":False,"run_id":RUN_ID,"activation_raw_physical_sha256":cap._raw,"activation_sha256":cap._canonical,"issued_at_utc":_utc(cap._issued_at),"expires_at_utc":_utc(cap._expires),"bindings":dict(cap._bindings),"recorded_at_utc":now}
 body=obs.get("body"); request={"schema_version":"har1r5-license-evidence.v1","record_type":"REQUEST","terminal":False,"sequence":1,"method":"GET","requested_url":URL,"request_headers":HEADERS,"request_attempted":obs["attempted"],"status_code":obs.get("status_code"),"final_url":obs.get("final_url"),"content_type":obs.get("content_type"),"content_type_values":obs.get("content_type_values",[]),"header_bytes":obs.get("header_bytes",0),"location":obs.get("location",[]),"set_cookie":obs.get("set_cookie",[]),"set_cookie_reused":False,"etag":obs.get("etag",[]),"last_modified":obs.get("last_modified",[]),"date":obs.get("date",[]),"server_time_used_for_available_at":False,"response_bytes":len(body) if body is not None else 0,"body_sha256":_sha(body) if body is not None else None,"raw_path":RAW_PATH if body is not None else None,"request_elapsed_ms":obs["elapsed_ms"],"cumulative_network_read_elapsed_ms":obs["elapsed_ms"],"received_at_utc":obs["received"],"persisted_at_utc":now,"admitted_at_utc":now,"available_at_utc":max(obs["received"],now),"outcome":"SUCCESS" if not obs["errors"] else "FAILURE","errors":obs["errors"],"transport_error":obs.get("transport_error")}
 state="SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW" if not obs["errors"] and all(candidate.get(n,{}).get("line_numbers") for n in ("identity_candidate","copyright","grant","conditions","warranty","liability")) else "SEALED_NOT_LICENSE_WAIT_DATA"
 terminal={"schema_version":"har1r5-license-evidence.v1","record_type":"TERMINAL","terminal":True,"run_id":RUN_ID,"candidate":candidate,"candidate_state":state,"legal_conclusion":False,"archive_scope_automatic_judgment":False,"total_elapsed_ms":request["request_elapsed_ms"],"available_at_utc":request["available_at_utc"]}
 return [activation,request,terminal]
def _write_evidence(root,records):
 previous="0"*64; lines=[]
 for r in records:
  line=_canon(dict(r,previous_raw_line_sha256=previous)); lines.append(line); previous=_sha(line+b"\n")
 _write_r4(root,EVIDENCE_PATH,b"\n".join(lines)+b"\n")
def replay_evidence(root=ROOT,observations=None):
 if observations is None:raise EvidenceError("manifest/replay requires live observations")
 if type(observations) is not dict:raise EvidenceError("live observation mapping")
 # This is diagnostic replay only.  Acceptance additionally requires the
 # execution-scoped observation retained in a claimed RunReceipt below.
 observations=_strict(_canon(observations)); validate_static_files(ROOT); replay_predecessors(ROOT)
 raw=_read(root,EVIDENCE_PATH); lines=raw[:-1].split(b"\n") if raw.endswith(b"\n") and b"\r" not in raw else []
 if len(lines)!=3:raise EvidenceError("three lines")
 prev="0"*64; records=[]
 for line in lines:
  d=_strict(line)
  if line!=_canon(d) or d.get("previous_raw_line_sha256")!=prev:raise EvidenceError("canonical chain")
  prev=_sha(line+b"\n"); records.append(d)
 a,q,t=records
 af={"schema_version","record_type","terminal","run_id","activation_raw_physical_sha256","activation_sha256","issued_at_utc","expires_at_utc","bindings","recorded_at_utc","previous_raw_line_sha256"}
 qf={"schema_version","record_type","terminal","sequence","method","requested_url","request_headers","request_attempted","status_code","final_url","content_type","content_type_values","header_bytes","location","set_cookie","set_cookie_reused","etag","last_modified","date","server_time_used_for_available_at","response_bytes","body_sha256","raw_path","request_elapsed_ms","cumulative_network_read_elapsed_ms","received_at_utc","persisted_at_utc","admitted_at_utc","available_at_utc","outcome","errors","transport_error","previous_raw_line_sha256"}
 tf={"schema_version","record_type","terminal","run_id","candidate","candidate_state","legal_conclusion","archive_scope_automatic_judgment","total_elapsed_ms","available_at_utc","previous_raw_line_sha256"}
 if set(a)!=af or set(q)!=qf or set(t)!=tf:raise EvidenceError("exact schema")
 if not (type(a["schema_version"]) is str and a["schema_version"]=="har1r5-license-evidence.v1" and type(a["record_type"]) is str and a["record_type"]=="ACTIVATION" and a["terminal"] is False and type(a["run_id"]) is str and a["run_id"]==RUN_ID and type(q["schema_version"]) is str and q["schema_version"]=="har1r5-license-evidence.v1" and type(q["record_type"]) is str and q["record_type"]=="REQUEST" and q["terminal"] is False and type(q["sequence"]) is int and not isinstance(q["sequence"],bool) and q["sequence"]==1 and type(q["method"]) is str and q["method"]=="GET" and type(q["requested_url"]) is str and q["requested_url"]==URL and _exact(q["request_headers"],HEADERS) and q["request_attempted"] is True and q["set_cookie_reused"] is False and q["server_time_used_for_available_at"] is False and type(t["schema_version"]) is str and t["schema_version"]=="har1r5-license-evidence.v1" and type(t["record_type"]) is str and t["record_type"]=="TERMINAL" and t["terminal"] is True and type(t["run_id"]) is str and t["run_id"]==RUN_ID and t["legal_conclusion"] is False and t["archive_scope_automatic_judgment"] is False):raise EvidenceError("fixed values")
 if any(type(a[k]) is not str or len(a[k])!=64 for k in ("activation_raw_physical_sha256","activation_sha256")) or type(a["bindings"]) is not dict or any(type(q[k]) is not int or isinstance(q[k],bool) for k in ("header_bytes","response_bytes","request_elapsed_ms","cumulative_network_read_elapsed_ms")) or q["header_bytes"]<0 or q["header_bytes"]>65536 or any(type(q[k]) is not list or any(type(x) is not str for x in q[k]) for k in ("content_type_values","location","set_cookie","etag","last_modified","date","errors")) or type(q["outcome"]) is not str or q["outcome"] not in {"SUCCESS","FAILURE"} or q["transport_error"] is not None and type(q["transport_error"]) is not str or type(t["candidate"]) is not dict or type(t["candidate_state"]) is not str or t["candidate_state"] not in {"SEALED_LICENSE_CANDIDATE_PENDING_HUMAN_SOL_REVIEW","SEALED_NOT_LICENSE_WAIT_DATA"} or type(t["total_elapsed_ms"]) is not int or isinstance(t["total_elapsed_ms"],bool):raise EvidenceError("request types")
 activation_raw=_read(root,ACTIVATION_PATH); activation_doc=_strict(activation_raw)
 activation_fields={"schema_version","decision_id","permission","issued_at_utc","expires_at_utc","bindings","canonical_self_digest","activation_sha256"}
 activation_meta={"algorithm":"SHA-256_CANONICAL_JSON","digest_field":"activation_sha256","domain_prefix_utf8":"msta-hed/har1r5-raw-license-candidate-activation/v1"}
 if set(activation_doc)!=activation_fields or (activation_doc.get("schema_version"),activation_doc.get("decision_id"),activation_doc.get("permission")) != ("har1r5-raw-license-candidate-activation.v1","SOL_HAR1R5_RAW_LICENSE_CANDIDATE_ACTIVATION.v1","ONE_GET_LICENSE_RAW_CANDIDATE") or not _exact(activation_doc.get("canonical_self_digest"),activation_meta) or _sha(activation_raw)!=a["activation_raw_physical_sha256"] or _digest(activation_doc,"activation_sha256","msta-hed/har1r5-raw-license-candidate-activation/v1")!=a["activation_sha256"] or not _exact(activation_doc.get("bindings"),a["bindings"]) or not _exact(activation_doc.get("bindings"),_activation_bindings()) or not _exact((activation_doc.get("issued_at_utc"),activation_doc.get("expires_at_utc")),(a["issued_at_utc"],a["expires_at_utc"])):raise EvidenceError("activation replay")
 for f in ("issued_at_utc","expires_at_utc","recorded_at_utc"):_parse_utc(a[f])
 if not 0<_parse_utc(a["expires_at_utc"])-_parse_utc(a["issued_at_utc"])<=900:raise EvidenceError("activation TTL")
 for f in ("received_at_utc","persisted_at_utc","admitted_at_utc","available_at_utc"):_parse_utc(q[f])
 if not a["issued_at_utc"]<=a["recorded_at_utc"]<=a["expires_at_utc"] or not q["received_at_utc"]<=q["persisted_at_utc"]<=q["admitted_at_utc"] or q["available_at_utc"]!=max(q["received_at_utc"],q["persisted_at_utc"],q["admitted_at_utc"]) or q["request_elapsed_ms"]<0 or (q["request_elapsed_ms"]>=20000 and q["transport_error"]!="REQUEST_DEADLINE_EXCEEDED") or q["cumulative_network_read_elapsed_ms"]!=q["request_elapsed_ms"] or t["total_elapsed_ms"]!=q["request_elapsed_ms"] or t["available_at_utc"]!=q["available_at_utc"]:raise EvidenceError("time ledger")
 live={k:q[k] for k in ("status_code","final_url","content_type","content_type_values","header_bytes","location","set_cookie","etag","last_modified","date","response_bytes","body_sha256","outcome","errors","transport_error")}
 if not _exact(live,observations):raise EvidenceError("same-run observation")
 if q["raw_path"] is not None:
  if q["raw_path"]!=RAW_PATH or type(q["status_code"]) is not int or type(q["final_url"]) is not str or (len(q["content_type_values"])==1 and type(q["content_type"]) is not str) or (len(q["content_type_values"])!=1 and q["content_type"] is not None) or type(q["body_sha256"]) is not str or q["transport_error"] is not None:raise EvidenceError("response types")
  body=_read(root,RAW_PATH)
  if len(body)!=q["response_bytes"] or _sha(body)!=q["body_sha256"]:raise EvidenceError("raw swap")
  valid=[]
  if q["status_code"]!=200:valid.append("HTTP_STATUS")
  if q["final_url"]!=URL:valid.append("FINAL_URL")
  if len(q["content_type_values"])!=1:valid.append("CONTENT_TYPE_CARDINALITY")
  elif q["content_type"]!=q["content_type_values"][0] or not q["content_type"].lower().startswith("text/plain"):valid.append("CONTENT_TYPE")
  if not body:valid.append("EMPTY_BODY")
  if body.startswith(b"\xef\xbb\xbf"):valid.append("UTF8_BOM")
  if b"\0" in body:valid.append("NUL")
  try:body.decode("utf-8","strict")
  except UnicodeDecodeError:valid.append("UTF8")
  candidate,state=_safe_extract(body)
  if any(code in valid for code in ("UTF8_BOM","NUL")) or candidate["bytes"]!=len(body):state="SEALED_NOT_LICENSE_WAIT_DATA"
  if valid:state="SEALED_NOT_LICENSE_WAIT_DATA"
  if q["errors"]!=valid or q["outcome"]!=("SUCCESS" if not valid else "FAILURE") or not _exact(t["candidate"],candidate) or t["candidate_state"]!=state:raise EvidenceError("derived response")
 else:
  if q["status_code"] is not None or q["final_url"] is not None or q["content_type"] is not None or q["content_type_values"]!=[] or _exists(root,RAW_PATH) or q["body_sha256"] is not None or q["response_bytes"]!=0 or q["outcome"]!="FAILURE" or type(q["transport_error"]) is not str or not q["transport_error"] or q["errors"] != [q["transport_error"]] or t["candidate_state"]!="SEALED_NOT_LICENSE_WAIT_DATA" or not _exact(t["candidate"],_empty_candidate(None)):raise EvidenceError("raw iff")
 return records
def _manifest(root,records,completed):
 a,q,t=records; d={"schema_version":"har1r5-license-manifest.v1","run_id":RUN_ID,"activation_raw_physical_sha256":a["activation_raw_physical_sha256"],"activation_sha256":a["activation_sha256"],"evidence_path":EVIDENCE_PATH,"evidence_physical_sha256":_sha(_read(root,EVIDENCE_PATH)),"request":{k:q[k] for k in ("status_code","final_url","content_type","content_type_values","header_bytes","location","set_cookie","etag","last_modified","date","response_bytes","body_sha256","raw_path","outcome","errors","available_at_utc")},"candidate":t["candidate"],"candidate_state":t["candidate_state"],"terminal":{"legal_conclusion":False,"archive_scope_automatic_judgment":False,"total_elapsed_ms":t["total_elapsed_ms"]},"completed_at_utc":completed,"canonical_self_digest":{"algorithm":"SHA-256_CANONICAL_JSON","digest_field":"manifest_sha256","domain_prefix_utf8":"msta-hed/har1r5-license-manifest/v1"}}
 d["manifest_sha256"]=_sha(b"msta-hed/har1r5-license-manifest/v1\0"+_canon(d)); return d
def validate_manifest(root=ROOT,receipt=None):
 state=_claim_run_receipt(root,receipt); records=replay_evidence(root,_strict(state["live_raw"])); raw=_read(root,MANIFEST_PATH); d=_strict(raw)
 if raw!=_canon(d) or _digest(d,"manifest_sha256","msta-hed/har1r5-license-manifest/v1")!=d["manifest_sha256"]:raise EvidenceError("manifest canonical")
 _parse_utc(d["completed_at_utc"]); expected=_manifest(root,records,d["completed_at_utc"])
 if not _exact(d,expected):raise EvidenceError("manifest derived")
 if (records[0]["activation_raw_physical_sha256"],records[0]["activation_sha256"]) != (state["activation_raw"],state["activation_canonical"]):raise EvidenceError("run receipt activation binding")
 _bound_outputs(root,state)
 return d
def _observe(response,started,monotonic,wall):
 body=None
 try:
  pairs,hbytes,loc,cookie,etag,last,date,ctype=_headers(response); chunks=[]; total=0
  while True:
   chunk=response.read(65537-total)
   if type(chunk) is not bytes:raise ProtocolViolation("body")
   if not chunk:break
   total+=len(chunk)
   if total>65536:raise ProtocolViolation("HALT_RESOURCE_CAP_BODY")
   chunks.append(chunk)
  body=b"".join(chunks)
  status=getattr(response,"status",getattr(response,"code",None)); final=response.geturl()
  if type(status) is not int or type(final) is not str:raise ProtocolViolation("response")
  errors=[]
  if status!=200:errors.append("HTTP_STATUS")
  if final!=URL:errors.append("FINAL_URL")
  if len(ctype)!=1:errors.append("CONTENT_TYPE_CARDINALITY")
  elif not ctype[0].lower().startswith("text/plain"):errors.append("CONTENT_TYPE")
  if not body:errors.append("EMPTY_BODY")
  if body.startswith(b"\xef\xbb\xbf"):errors.append("UTF8_BOM")
  if b"\0" in body:errors.append("NUL")
  try:body.decode("utf-8","strict")
  except UnicodeDecodeError:errors.append("UTF8")
  return {"attempted":True,"status_code":status,"final_url":final,"content_type":ctype[0] if len(ctype)==1 else None,"content_type_values":ctype,"header_bytes":hbytes,"location":loc,"set_cookie":cookie,"etag":etag,"last_modified":last,"date":date,"body":body,"elapsed_ms":int((monotonic()-started)*1000),"received":_utc(wall()),"errors":errors,"transport_error":None}
 finally:
  response.close()
def _failure(error,started,monotonic,wall):return {"attempted":True,"status_code":None,"final_url":None,"content_type":None,"content_type_values":[],"header_bytes":0,"location":[],"set_cookie":[],"etag":[],"last_modified":[],"date":[],"body":None,"elapsed_ms":int((monotonic()-started)*1000),"received":_utc(wall()),"errors":[error],"transport_error":error}
def _live(obs):return {k:(len(obs["body"]) if k=="response_bytes" and obs.get("body") is not None else 0 if k=="response_bytes" else _sha(obs["body"]) if k=="body_sha256" and obs.get("body") is not None else ("SUCCESS" if not obs["errors"] else "FAILURE") if k=="outcome" else obs.get(k)) for k in ("status_code","final_url","content_type","content_type_values","header_bytes","location","set_cookie","etag","last_modified","date","response_bytes","body_sha256","outcome","errors","transport_error")}
def _execute_with_transport(cap,transport,root=ROOT,monotonic=time.monotonic,wall=time.time,deadline_factory=None):
 R3._require_production_alarm_available(); _consume(cap); _pre_tcp(cap,root)
 started=monotonic(); factory=R3._posix_deadline if deadline_factory is None else deadline_factory; response=None
 try:
  guard=factory(20.0); guard.__enter__()
 except Exception as e:raise ContractError("deadline guard enter") from e
 try:
  try:
   try: response=transport("GET",URL,20.0,dict(HEADERS))
   except urllib.error.HTTPError as e: response=e
   obs=_observe(response,started,monotonic,wall); response=None
  except Exception as e:
   if response is not None:
    try:response.close()
    except Exception: pass
   deadline_type=R3.R2_SAFETY._DeadlineExceeded
   code="REQUEST_DEADLINE_EXCEEDED" if type(e) is deadline_type else str(e) if isinstance(e,ProtocolViolation) and str(e) else type(e).__name__
   obs=_failure(code,started,monotonic,wall)
 finally:
  try: guard.__exit__(None,None,None)
  except Exception as e: raise ContractError("deadline guard exit") from e
 if obs["elapsed_ms"]>=20000:
  obs.update({"body":None,"status_code":None,"final_url":None,"content_type":None,"content_type_values":[],"header_bytes":0,"location":[],"set_cookie":[],"etag":[],"last_modified":[],"date":[],"errors":["REQUEST_DEADLINE_EXCEEDED"],"transport_error":"REQUEST_DEADLINE_EXCEEDED"})
 candidate=_empty_candidate(None); state="SEALED_NOT_LICENSE_WAIT_DATA"
 # This nonce and observation identity are born after _observe returns and
 # never leave this execution scope except through the opaque receipt.
 live_raw=_canon(_live(obs)); observe_identity=object(); execution_nonce=object()
 if obs["body"] is not None:
  candidate,state=_safe_extract(obs["body"]); _write_r4(root,RAW_PATH,obs["body"])
 records=_line_records(cap,obs,candidate if obs["body"] is not None else candidate,_utc(wall())); _write_evidence(root,records)
 checked=replay_evidence(root,_strict(live_raw)); manifest=_manifest(root,checked,_utc(wall())); _write_r4(root,MANIFEST_PATH,_canon(manifest))
 receipt=RunReceipt(execution_nonce); info=os.stat(root)
 state={"phase":"SEALED","receipt":receipt,"nonce":execution_nonce,"observe_identity":observe_identity,"observation":obs,"observation_identity":id(obs),"live_raw":live_raw,"cap":cap,"cap_id":id(cap),"activation_raw":cap._raw,"activation_canonical":cap._canonical,"root_dev":info.st_dev,"root_ino":info.st_ino,"raw_exists":_exists(root,RAW_PATH),"raw_physical":_sha(_read(root,RAW_PATH)) if _exists(root,RAW_PATH) else None,"evidence_physical":_sha(_read(root,EVIDENCE_PATH)),"manifest_physical":_sha(_read(root,MANIFEST_PATH))}
 with _run_registry_lock:_run_registry[id(receipt)]=state
 return validate_manifest(root,receipt)
def execute_license_raw(capability):
 # This order is intentional: alarm before opener, capability consumption, or output.
 R3._require_production_alarm_available(); opener=urllib.request.build_opener(R4._ForcedHttpsProxyHandler(),R4._NoRedirect())
 def transport(method,url,timeout,headers):return opener.open(urllib.request.Request(url,method=method,headers=headers),timeout=timeout)
 return _execute_with_transport(capability,transport)
