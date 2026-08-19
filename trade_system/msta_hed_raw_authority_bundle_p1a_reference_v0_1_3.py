"""Pure E0 synthetic genesis-admission reference.  It performs no I/O."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime
from typing import Any, Mapping

EXPECTED_CONTRACT_SHA256 = "222b8362b2260ed76e67afc25a1729feb7de9b77eb699717709d14fd4da9a5f1"
PINNED_ROOT = {"schema_type":"PinnedSyntheticTrustRootAuthorityV1","trust_root_id":"PINNED-SYNTHETIC-TRUST-ROOT-1","key_fingerprint":"a"*64,"not_after":"2026-12-31T00:00:00Z"}
ROOT_DOMAIN = "msta/r3/pinned-root/v1"

def _canon(v: Any) -> bytes: return json.dumps(v, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
def _hash(domain: str, v: Any) -> str: return hashlib.sha256(domain.encode()+b"\0"+_canon(v)).hexdigest()
def _utc(v: Any) -> datetime:
    if type(v) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",v): raise ValueError
    return datetime.fromisoformat(v[:-1]+"+00:00")
def _sha(v: Any) -> bool: return type(v) is str and bool(re.fullmatch(r"[0-9a-f]{64}",v))

def _decision(contract: Mapping[str,Any], status: str, reason: str, receipt: Any=None, admission: Any=None) -> dict[str,Any]:
    v={"schema_type":"ValidationDecisionV1","status":status,"reason_code":reason,"receipt":receipt,"admission":admission}
    v["validation_decision_digest"]=_hash(contract["schemas"]["ValidationDecisionV1"]["domain"],v); return v

def _schema(contract: Mapping[str,Any], name: str, o: Any) -> bool:
    s=contract["schemas"].get(name)
    if not isinstance(s,dict) or type(o) is not dict or set(o)!=set(s["exact_fields"]) or o.get("schema_type")!=name:return False
    f=s["digest_field"]
    return _sha(o.get(f)) and o[f]==_hash(s["domain"],{k:v for k,v in o.items() if k!=f})

def _field_types(contract: Mapping[str,Any], name: str, o: Mapping[str,Any]) -> bool:
    f=o
    if name not in contract.get("schemas",{}): return False
    if name=="ValidatorInputV1":
        return type(f["payload_byte_length"]) is int and f["payload_byte_length"]>=0 and all(_sha(f[k]) for k in ("payload_sha256","validator_input_digest")) and all(f[k] is None or _sha(f[k]) for k in ("prior_cursor_digest","previous_receipt_digest","expected_prefix_digest")) and type(f["records"]) is list
    if name=="RawRecordEnvelopeV1": return type(f["revision_ordinal"]) is int and not isinstance(f["revision_ordinal"],bool) and all(type(f[k]) is str for k in ("raw_record_id","logical_record_id","revision_id","event_at","available_at"))
    if name=="TransformAuthorityV1": return type(f["authorized"]) is bool and type(f["transform_id"]) is str and _sha(f["transform_digest"])
    if name=="CoverageProofV1": return type(f["proof_kind"]) is str and type(f["proof_ref"]) is str and _sha(f["proof_digest"]) and type(f["coverage_disposition"]) is str
    if name=="ExternalTipCommitmentV1":
        try:return type(f["tip_id"]) is str and _sha(f["tip_digest"]) and isinstance(_utc(f["committed_at"]),datetime)
        except (ValueError,KeyError,TypeError):return False
    if name=="ExactV05EvidenceBindingV1":
        e=f["evidence"]
        try: causal=_utc(e["available_at"])
        except (ValueError,KeyError,TypeError): return False
        return type(e) is dict and set(e)=={"evidence_id","available_at","perspective_id","dependency_group","target_ids","direction","ordinal_strength","quality","source_version"} and type(e["target_ids"]) is list and e["target_ids"]==sorted(set(e["target_ids"])) and bool(e["target_ids"]) and all(type(x) is str and x for x in e["target_ids"]) and all(type(e[k]) is str and e[k] for k in ("evidence_id","perspective_id","dependency_group","direction","ordinal_strength","quality","source_version")) and e["perspective_id"] in ("PERSPECTIVE-SYNTHETIC-E0","PERSPECTIVE-SYNTHETIC-E0-ALT") and e["direction"] in ("SUPPORT","SOFT_CONTRADICTION","HARD_FALSIFIER") and e["ordinal_strength"] in ("WEAK","MODERATE","STRONG") and e["quality"]=="VALID" and e["source_version"]=="SYNTHETIC-SOURCE-V1" and f["method_contract_physical_sha256"]=="18ef5234cb018d1a89252733a6d66903a145864031a2c8d663f021abe79740b0" and f["method_contract_canonical_sha256"]=="39b9044cd172d239ab3d81a990bbe787035fbe618f6cc500274dcf2e93e067fd"
    return False

def _active_alias(v: Any) -> bool:
    if type(v) is str:
        u=v.upper(); return "ACTIVE_G1" in u or "APPLICATION%20SUPPORT" in u or "APPLICATION_SUPPORT" in u or "SEEN" in u
    if type(v) is list:return any(_active_alias(x) for x in v)
    if type(v) is dict:return any(_active_alias(x) for x in v.values())
    return False

def _validate_p1a_r3_inner(contract: Mapping[str,Any], candidate: Mapping[str,Any]) -> dict[str,Any]:
    """Validate a supplied synthetic genesis candidate without reading any external state."""
    c=dict(contract); supplied=c.pop("contract_sha256",None)
    if supplied!=EXPECTED_CONTRACT_SHA256 or supplied!=_hash("msta-hed/raw-authority-bundle-contract/v1",c): return _decision(contract,"REJECTED","E_CONTRACT_DIGEST")
    if type(candidate) is not dict or set(candidate)!={"input"}: return _decision(contract,"REJECTED","E_TRUST_ROOT_MISMATCH")
    if _active_alias(candidate): return _decision(contract,"REJECTED","E_ACTIVE_G1_FORBIDDEN")
    inp=candidate.get("input") if type(candidate) is dict else None
    if not _schema(contract,"ValidatorInputV1",inp) or not _field_types(contract,"ValidatorInputV1",inp): return _decision(contract,"REJECTED","E_FIELD_TYPE")
    if inp["lane"]!="SYNTHETIC_CONTRACT": return _decision(contract,"REJECTED","E_LANE_NOT_ALLOWED")
    if inp["capability"]!="SUPPLIED_PAYLOAD_ONLY": return _decision(contract,"REJECTED","E_CAPABILITY_NOT_ALLOWED")
    if inp["prior_cursor_digest"] is not None:return _decision(contract,"REJECTED","E_CURSOR_REFERENCE_FORBIDDEN_P1A")
    if inp["previous_receipt_digest"] is not None or inp["expected_prefix_digest"] is not None:return _decision(contract,"REJECTED","E_PREFIX_REFERENCE_FORBIDDEN_P1A")
    if inp["trust_root_id"]!=PINNED_ROOT["trust_root_id"]:return _decision(contract,"REJECTED","E_TRUST_ROOT_MISMATCH")
    try: now=_utc(inp["decision_time"]); root_end=_utc(PINNED_ROOT["not_after"])
    except ValueError:return _decision(contract,"REJECTED","E_FIELD_TYPE")
    if now>root_end:return _decision(contract,"REJECTED","E_TRUST_CLOCK")
    if inp["payload_byte_length"]==0:
        if inp["records"] or any(inp[k] is not None for k in ("receipt","admission","transform_authority","coverage_proof","external_tip","v05_binding")):return _decision(contract,"REJECTED","E_RECEIPT_EMPTY_RULE")
        return _decision(contract,"VALID_EMPTY_NOT_ADMITTED","OK_VALID_EMPTY_NOT_ADMITTED")
    if inp["receipt"] is None or inp["admission"] is None:return _decision(contract,"REJECTED","E_NONEMPTY_RECEIPT_REQUIRED")
    if set(inp["receipt"])!={"receipt_id","result_class"} or inp["receipt"]["result_class"]!="ACCEPTED":return _decision(contract,"REJECTED","E_RESULT_CLASS_INVALID")
    if set(inp["admission"])!={"admission_id","status"} or inp["admission"]["status"]!="ADMITTED":return _decision(contract,"REJECTED","E_RESULT_CLASS_INVALID")
    if len(inp["records"])!=1 or not _schema(contract,"RawRecordEnvelopeV1",inp["records"][0]) or not _field_types(contract,"RawRecordEnvelopeV1",inp["records"][0]):return _decision(contract,"REJECTED","E_RECORD_CARDINALITY")
    r=inp["records"][0]
    if len({r["raw_record_id"],r["logical_record_id"],r["revision_id"]})!=3 or r["revision_operation"]!="INITIAL" or r["predecessor_revision_id"] is not None or r["revision_ordinal"]!=0:return _decision(contract,"REJECTED","E_RECORD_NOT_INITIAL_GENESIS")
    try:
        if not (_utc(r["event_at"])<=_utc(r["available_at"])<=now):return _decision(contract,"REJECTED","E_TRUST_CLOCK")
    except ValueError:return _decision(contract,"REJECTED","E_FIELD_TYPE")
    for name,key in (("TransformAuthorityV1","transform_authority"),("CoverageProofV1","coverage_proof"),("ExternalTipCommitmentV1","external_tip")):
        if not _schema(contract,name,inp[key]) or not _field_types(contract,name,inp[key]):return _decision(contract,"REJECTED","E_FIELD_TYPE")
    t,p,tip,v5=inp["transform_authority"],inp["coverage_proof"],inp["external_tip"],inp["v05_binding"]
    if t["transform_id"]!="SYNTHETIC-TRANSFORM-1" or not t["authorized"]:return _decision(contract,"REJECTED","E_TRANSFORM_NOT_AUTHORIZED")
    if p["coverage_disposition"]!="CLEAR":return _decision(contract,"REJECTED","E_COVERAGE_NOT_CLEAR")
    if p["proof_kind"] not in ("CONTINUOUS_OBSERVED","NO_ACTIVITY_AUTHORITY_BOUND"):return _decision(contract,"REJECTED","E_PROOF_NOT_AUTHORIZED")
    if tip["tip_id"]!="SYNTHETIC-TIP-1":return _decision(contract,"REJECTED","E_EXTERNAL_TIP_IDENTITY")
    if not _schema(contract,"ExactV05EvidenceBindingV1",v5) or not _field_types(contract,"ExactV05EvidenceBindingV1",v5):return _decision(contract,"REJECTED","E_V05_CARRIER_NOT_SUPPORTED_P1A")
    return _decision(contract,"ADMITTED","OK_ADMITTED",inp["receipt"],inp["admission"])

def validate_p1a_r3(contract: Mapping[str,Any], candidate: Mapping[str,Any]) -> dict[str,Any]:
    """Total public entry point: malformed inputs return an exact rejection decision."""
    try:
        return _validate_p1a_r3_inner(contract, candidate)
    except Exception:
        domain = "msta/r3/decision/v1"
        value={"schema_type":"ValidationDecisionV1","status":"REJECTED","reason_code":"E_CONTRACT_DIGEST","receipt":None,"admission":None}
        value["validation_decision_digest"]=_hash(domain,value)
        return value
