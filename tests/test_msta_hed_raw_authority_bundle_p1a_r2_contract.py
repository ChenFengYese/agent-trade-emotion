"""P1A-R2 static reference validator.  No runtime adapter, source, or I/O exists here."""
from __future__ import annotations
import copy, hashlib, json, re, unittest
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CP=ROOT/'config/msta_hed_raw_authority_bundle.p1a_contract.v0_1_2.json'
FP=ROOT/'config/msta_hed_raw_authority_bundle.p1a_synthetic_contract.v0_1_2.json'
CONTRACT=json.loads(CP.read_text()); FIXTURE=json.loads(FP.read_text()); S=CONTRACT['schemas']; E=CONTRACT['closed_enums']

def canon(x): return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
def dh(domain,x): return hashlib.sha256(domain.encode()+b'\0'+canon(x)).hexdigest()
def dfield(name): return S[name]['fields'][-1]
def sign(name,v):
    assert set(v)==set(S[name]['fields'][:-1]); out=dict(v); out[dfield(name)]=dh(S[name]['domain'],out); return out
def resign(name,o): o[dfield(name)]=dh(S[name]['domain'],{k:v for k,v in o.items() if k!=dfield(name)})
def sha(x): return type(x) is str and bool(re.fullmatch(r'[0-9a-f]{64}',x))
def utc(x):
    if type(x) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',x): raise ValueError
    return datetime.fromisoformat(x[:-1]+'+00:00')
def path(x): return type(x) is str and bool(x) and not any(z in x for z in ('%','~','\\')) and not x.startswith('/') and not re.match(r'^[A-Za-z]:',x) and all(p not in ('','.','..') for p in x.split('/'))
def idem(r): return dh('msta/p1a/idempotency/v1',[r['adapter_contract_digest'],r['source_snapshot_digest'],r['prior_cursor_digest'] or 'NULL',r['supplied_payload_sha256'],r['supplied_payload_byte_length'],r['decision_time'],r['expected_prefix_digest'] or 'NULL'])
def sig(bundle,material): return hashlib.sha256(b'test-seal\0'+bundle.encode()+material.encode()).hexdigest()

def schema(name,o):
    if type(o) is not dict or set(o)!=set(S[name]['fields']) or o.get('schema_type')!=name: return 'MSTA_P1A_E_SCHEMA_EXACT'
    if not sha(o[dfield(name)]) or o[dfield(name)]!=dh(S[name]['domain'],{k:v for k,v in o.items() if k!=dfield(name)}): return 'MSTA_P1A_E_SCHEMA_EXACT'
    for k,v in o.items():
        if k.endswith('_digest') and k!=dfield(name) and v is not None and not sha(v): return 'MSTA_P1A_E_SCHEMA_EXACT'
    if name=='RawArtifactDescriptorV1' and not path(o['logical_path']): return 'MSTA_P1A_E_PATH_INVALID'
    if name in ('AdapterReceiptV1','AdapterResultV1') and (type(o['reason_codes']) is not list or any(x not in E['rejection_reasons'] for x in o['reason_codes'])): return 'MSTA_P1A_E_SCHEMA_EXACT'
    if name in ('AdapterReceiptV1','AdapterResultV1') and (type(o['record_digests']) is not list or len(o['record_digests'])!=len(set(o['record_digests'])) or type(o['coverage_event_digests']) is not list or len(o['coverage_event_digests'])!=len(set(o['coverage_event_digests']))): return 'MSTA_P1A_E_SCHEMA_EXACT'
    return None

def coverage_reason(c,decision):
    if schema('CoverageEventV1',c): return schema('CoverageEventV1',c)
    try: ok=utc(c['interval_start'])<=utc(c['interval_end'])<=utc(c['observed_at'])<=utc(decision)
    except ValueError: ok=False
    if not ok or c['coverage_state'] not in E['coverage_states'] or c['coverage_cause'] not in E['coverage_causes']: return 'MSTA_P1A_E_COVERAGE_PROOF'
    proof=all(c[k] is not None for k in ('proof_ref','proof_digest')) and sha(c['proof_digest'])
    if c['coverage_state']=='CONFIRMED_NO_ACTIVITY' and not (c['proof_kind']=='NO_ACTIVITY_SOURCE_PROOF' and proof): return 'MSTA_P1A_E_COVERAGE_PROOF'
    if c['coverage_state']=='EXPECTED_SNAPSHOT_CADENCE' and not (c['proof_kind']=='CADENCE_CONTRACT' and proof and type(c['expected_cadence_seconds']) is int and c['expected_cadence_seconds']>0): return 'MSTA_P1A_E_COVERAGE_PROOF'
    if c['coverage_state']=='NATIVE_SEQUENCE_GAP' and not (c['proof_kind']=='NATIVE_SEQUENCE_PROOF' and proof and type(c['sequence_start']) is int and type(c['sequence_end']) is int and c['sequence_start']<=c['sequence_end']): return 'MSTA_P1A_E_COVERAGE_PROOF'
    if c['coverage_state']=='MARKET_HALT' and not (c['proof_kind']=='MARKET_HALT_AUTHORITY' and proof): return 'MSTA_P1A_E_COVERAGE_PROOF'
    if c['generation_boundary'] and not (c['coverage_state']=='TRANSPORT_GAP' and c['coverage_cause']=='CURSOR_RESET' and c['previous_generation_id'] and c['new_generation_id']==c['source_generation_id'] and c['previous_generation_id']!=c['new_generation_id']): return 'MSTA_P1A_E_INVALID_REVISION'
    return None

def disposition(cs):
    if not cs: return 'UNKNOWN'
    if any(c['coverage_cause']=='SCHEMA_REJECT' for c in cs): return 'BLOCKED'
    if any(c['coverage_cause']!='NONE' for c in cs): return 'BLOCKED'
    if any(c['coverage_state']=='UNKNOWN_COVERAGE' for c in cs): return 'UNKNOWN'
    return 'CLEAR' if all(c['coverage_state'] in ('CONTINUOUS_OBSERVED','CONFIRMED_NO_ACTIVITY','EXPECTED_SNAPSHOT_CADENCE','MARKET_HALT') for c in cs) else 'BLOCKED'

def bind():
    trust=sign('TrustedSealAuthoritySnapshotV1',{'schema_type':'TrustedSealAuthoritySnapshotV1','trust_snapshot_id':'TRUST-1','authority_id':'SEALER-1','algorithm':'TEST_DETERMINISTIC_SHA256','key_id':'KEY-1','public_key_fingerprint':'a'*64,'verification_material_digest':'b'*64,'external_tip_contract_digest':'c'*64,'external_tip_digest':'5'*64,'frozen_at':'2026-07-26T00:00:00Z'})
    src=sign('SourceAuthoritySnapshotV1',{'schema_type':'SourceAuthoritySnapshotV1','source_snapshot_id':'SRC-1','source_id':'SOURCE-1','source_generation_id':'GEN-1','source_contract_digest':'d'*64,'adapter_contract_digest':'e'*64,'frozen_at':'2026-07-26T00:00:00Z'})
    art=sign('RawArtifactDescriptorV1',{'schema_type':'RawArtifactDescriptorV1','artifact_id':'ART-1','source_snapshot_digest':src['source_snapshot_digest'],'logical_path':'raw/r2/a.ndjson','content_sha256':'f'*64,'byte_length':1,'captured_at':'2026-07-26T00:00:01Z'})
    rec=sign('RawRecordEnvelopeV1',{'schema_type':'RawRecordEnvelopeV1','raw_record_id':'RAW-1','logical_record_id':'LOG-1','revision_id':'REV-1','revision_operation':'INITIAL','predecessor_revision_id':None,'revision_ordinal':0,'revision_fork_id':'FORK-1','source_generation_id':'GEN-1','source_snapshot_digest':src['source_snapshot_digest'],'artifact_digest':art['artifact_digest'],'event_at':None,'published_at':None,'received_at':'2026-07-26T00:00:01Z','ingested_at':'2026-07-26T00:00:01Z','derived_at':'2026-07-26T00:00:01Z','actual_available_at':'2026-07-26T00:00:01Z','availability_kind':'ACTUAL','counterfactual_available_at':None,'reconstruction_basis':None,'payload_sha256':'1'*64,'record_state':'ACTIVE'})
    cov=sign('CoverageEventV1',{'schema_type':'CoverageEventV1','coverage_event_id':'COV-1','source_snapshot_digest':src['source_snapshot_digest'],'source_generation_id':'GEN-1','affected_scope':'SOURCE-1:METADATA','coverage_state':'CONTINUOUS_OBSERVED','coverage_cause':'NONE','interval_start':'2026-07-26T00:00:00Z','interval_end':'2026-07-26T00:00:01Z','observed_at':'2026-07-26T00:00:01Z','proof_kind':'NONE','proof_ref':None,'proof_digest':None,'expected_cadence_seconds':None,'sequence_start':None,'sequence_end':None,'generation_boundary':False,'previous_generation_id':None,'new_generation_id':None})
    cur=sign('AdapterCursorV1',{'schema_type':'AdapterCursorV1','cursor_id':'CUR-1','source_snapshot_digest':src['source_snapshot_digest'],'source_generation_id':'GEN-1','stream_scope':'SOURCE-1:METADATA','cursor_token':'T-1','cursor_ordinal':0,'observed_at':'2026-07-26T00:00:01Z','predecessor_cursor_digest':None})
    rq0={'schema_type':'AdapterRequestV1','request_id':'REQ-1','source_snapshot_digest':src['source_snapshot_digest'],'adapter_contract_digest':src['adapter_contract_digest'],'prior_cursor_digest':None,'supplied_payload_sha256':'2'*64,'supplied_payload_byte_length':1,'decision_time':'2026-07-26T00:00:02Z','expected_prefix_digest':None,'idempotency_key':'0'*64,'capabilities':['SUPPLIED_PAYLOAD_ONLY']};rq0['idempotency_key']=idem(rq0); req=sign('AdapterRequestV1',rq0)
    rp=sign('AdapterReceiptV1',{'schema_type':'AdapterReceiptV1','adapter_receipt_id':'RECEIPT-1','request_digest':req['adapter_request_digest'],'source_snapshot_digest':src['source_snapshot_digest'],'adapter_contract_digest':src['adapter_contract_digest'],'decision_time':req['decision_time'],'previous_receipt_digest':None,'expected_prefix_digest':None,'prior_cursor_digest':None,'next_cursor_digest':cur['cursor_digest'],'input_payload_sha256':req['supplied_payload_sha256'],'input_payload_byte_length':1,'result_class':'ACCEPTED','reason_codes':[],'record_digests':[rec['raw_record_digest']],'coverage_event_digests':[cov['coverage_event_digest']],'idempotency_key':req['idempotency_key']})
    rs=sign('AdapterResultV1',{'schema_type':'AdapterResultV1','request_digest':req['adapter_request_digest'],'receipt_digest':rp['adapter_receipt_digest'],'source_snapshot_digest':src['source_snapshot_digest'],'adapter_contract_digest':src['adapter_contract_digest'],'decision_time':req['decision_time'],'previous_receipt_digest':None,'expected_prefix_digest':None,'prior_cursor_digest':None,'next_cursor_digest':cur['cursor_digest'],'input_payload_sha256':req['supplied_payload_sha256'],'input_payload_byte_length':1,'result_class':'ACCEPTED','reason_codes':[],'record_digests':[rec['raw_record_digest']],'coverage_event_digests':[cov['coverage_event_digest']],'idempotency_key':req['idempotency_key']})
    bun=sign('RawAuthorityBundleManifestV1',{'schema_type':'RawAuthorityBundleManifestV1','bundle_id':'BUN-1','lane':'SYNTHETIC_CONTRACT','plan_id':'PLAN-1','registry_digest':'3'*64,'evidence_root_id':'ROOT-1','p1a_contract_digest':CONTRACT['contract_sha256'],'source_snapshot_digest':src['source_snapshot_digest'],'adapter_contract_digest':src['adapter_contract_digest'],'transform_digest':'4'*64,'artifact_digests':[art['artifact_digest']],'raw_record_digests':[rec['raw_record_digest']],'coverage_event_digests':[cov['coverage_event_digest']],'cursor_digest':cur['cursor_digest'],'adapter_receipt_digest':rp['adapter_receipt_digest'],'coverage_disposition':'CLEAR','created_at':'2026-07-26T00:00:02Z'})
    seal=sign('RawAuthoritySealV1',{'schema_type':'RawAuthoritySealV1','seal_id':'SEAL-1','trusted_authority_snapshot_digest':trust['trusted_authority_snapshot_digest'],'seal_authority_id':trust['authority_id'],'algorithm':trust['algorithm'],'key_id':trust['key_id'],'public_key_fingerprint':trust['public_key_fingerprint'],'verification_material_digest':trust['verification_material_digest'],'external_tip_contract_digest':trust['external_tip_contract_digest'],'sealed_bundle_digest':bun['bundle_digest'],'signed_payload_digest':bun['bundle_digest'],'external_tip_id':'TIP-1','external_tip_digest':trust['external_tip_digest'],'sealed_at':'2026-07-26T00:00:02Z','expires_at':'2026-07-27T00:00:02Z','seal_signature_digest':sig(bun['bundle_digest'],trust['verification_material_digest'])})
    cp={'schema_version':'v05-synthetic-binding-v1','carrier_id':'C-1','available_at':'2026-07-26T00:00:01Z'};op={'schema_version':'v05-synthetic-binding-v1','result_id':'R-1','decision_time':'2026-07-26T00:00:02Z'}
    v5=sign('V05CarrierBindingV1',{'schema_type':'V05CarrierBindingV1','carrier_type':'Evidence','carrier_payload':cp,'result_payload':op,'carrier_digest':dh('msta/v05-carrier/v1',cp),'result_digest':dh('msta/v05-result/v1',op)})
    ad=sign('EvidenceAdmissionContextV1',{'schema_type':'EvidenceAdmissionContextV1','admission_context_id':'ADM-1','v05_binding_digest':v5['binding_digest'],'raw_record_digest':rec['raw_record_digest'],'logical_record_id':rec['logical_record_id'],'revision_id':rec['revision_id'],'transform_digest':bun['transform_digest'],'coverage_membership_digests':[cov['coverage_event_digest']],'coverage_disposition':'CLEAR','bundle_digest':bun['bundle_digest'],'seal_digest':seal['seal_digest'],'expected_external_tip_digest':seal['external_tip_digest'],'expires_at':seal['expires_at'],'decision_time':'2026-07-26T00:00:03Z','lane':'SYNTHETIC_CONTRACT','admission_status':'ADMITTED','reason_codes':[]})
    records=[rec]
    return locals()

def validate(x):
    names=['trust','src','art','rec','cur','req','rp','rs','bun','seal','v5','ad']
    schemas=['TrustedSealAuthoritySnapshotV1','SourceAuthoritySnapshotV1','RawArtifactDescriptorV1','RawRecordEnvelopeV1','AdapterCursorV1','AdapterRequestV1','AdapterReceiptV1','AdapterResultV1','RawAuthorityBundleManifestV1','RawAuthoritySealV1','V05CarrierBindingV1','EvidenceAdmissionContextV1']
    for n,s in zip(names,schemas):
        r=schema(s,x[n])
        if r:return r
    cs=x['coverages'];
    if type(cs) is not list or not cs:return 'MSTA_P1A_E_COVERAGE_PROOF'
    for c in cs:
        r=coverage_reason(c,x['ad']['decision_time'])
        if r:return r
        if c['source_snapshot_digest']!=x['src']['source_snapshot_digest'] or c['source_generation_id']!=x['src']['source_generation_id'] or c['affected_scope']!='SOURCE-1:METADATA':return 'MSTA_P1A_E_IDENTITY_DRIFT'
    r,a,rec,cur,rq,rp,rs,b,se,t,v5,ad=[x[k] for k in ('src','art','rec','cur','req','rp','rs','bun','seal','trust','v5','ad')]
    aliases=[b['plan_id'],b['evidence_root_id'],cur['cursor_token'],a['logical_path']]
    if any('ACTIVE_G1' in z.upper() or 'APPLICATION%20SUPPORT' in z.upper() or 'APPLICATION_SUPPORT' in z.upper() or 'SEEN' in z.upper() for z in aliases):return 'MSTA_P1A_E_ACTIVE_G1_FORBIDDEN'
    if not path(a['logical_path']):return 'MSTA_P1A_E_PATH_INVALID'
    if b['p1a_contract_digest']!=CONTRACT['contract_sha256']:return 'MSTA_P1A_E_CONTRACT_DIGEST'
    if not (a['source_snapshot_digest']==r['source_snapshot_digest']==rec['source_snapshot_digest']==rq['source_snapshot_digest']==b['source_snapshot_digest'] and a['artifact_digest']==rec['artifact_digest'] and rq['adapter_contract_digest']==r['adapter_contract_digest']==b['adapter_contract_digest']):return 'MSTA_P1A_E_IDENTITY_DRIFT'
    try: clock=utc(rec['received_at'])<=utc(rec['ingested_at'])<=utc(rec['derived_at'])<=utc(rec['actual_available_at'])<=utc(ad['decision_time'])
    except ValueError:clock=False
    if not clock or utc(a['captured_at'])>utc(rq['decision_time']) or utc(rq['decision_time'])>utc(ad['decision_time']) or rec['availability_kind']!='ACTUAL' or rec['counterfactual_available_at'] is not None or rec['reconstruction_basis'] is not None:return 'MSTA_P1A_E_PIT_ORDER'
    if len({rec['raw_record_id'],rec['logical_record_id'],rec['revision_id']})!=3 or rec['revision_fork_id']!='FORK-1' or rec['revision_operation']!='INITIAL' or rec['predecessor_revision_id'] is not None or rec['revision_ordinal']!=0 or rec['record_state']!='ACTIVE':return 'MSTA_P1A_E_INVALID_REVISION'
    if (cur['cursor_ordinal']==0) != (cur['predecessor_cursor_digest'] is None):return 'MSTA_P1A_E_ADAPTER_CHAIN'
    if rq['idempotency_key']!=idem(rq):return 'MSTA_P1A_E_IDEMPOTENCY_FORMULA'
    fields=['source_snapshot_digest','adapter_contract_digest','decision_time','previous_receipt_digest','expected_prefix_digest','prior_cursor_digest','next_cursor_digest','input_payload_sha256','input_payload_byte_length','result_class','reason_codes','record_digests','coverage_event_digests','idempotency_key']
    if rp['request_digest']!=rq['adapter_request_digest'] or any(rp[k]!=(rq['source_snapshot_digest'] if k=='source_snapshot_digest' else rq['adapter_contract_digest'] if k=='adapter_contract_digest' else rq['decision_time'] if k=='decision_time' else rq['expected_prefix_digest'] if k in ('previous_receipt_digest','expected_prefix_digest') else rq['prior_cursor_digest'] if k=='prior_cursor_digest' else cur['cursor_digest'] if k=='next_cursor_digest' else rq['supplied_payload_sha256'] if k=='input_payload_sha256' else rq['supplied_payload_byte_length'] if k=='input_payload_byte_length' else rq['idempotency_key'] if k=='idempotency_key' else rp[k]) for k in fields):return 'MSTA_P1A_E_ADAPTER_CHAIN'
    if any(rs[k]!=rp[k] for k in fields) or rs['request_digest']!=rq['adapter_request_digest'] or rs['receipt_digest']!=rp['adapter_receipt_digest']:return 'MSTA_P1A_E_ADAPTER_CHAIN'
    if rp['result_class']=='ACCEPTED' and rp['reason_codes'] or rp['result_class'].startswith('REJECTED') and not rp['reason_codes'] or rq['supplied_payload_byte_length']>0 and not rs['receipt_digest'] or rp['result_class']=='EMPTY' and (rq['supplied_payload_byte_length']!=0 or rs['receipt_digest'] is not None or rp['record_digests'] or rp['coverage_event_digests']):return 'MSTA_P1A_E_ADAPTER_CHAIN'
    cds=[c['coverage_event_digest'] for c in cs]
    if len(cds)!=len(set(cds)) or rp['record_digests']!=[rec['raw_record_digest']] or rp['coverage_event_digests']!=cds or b['artifact_digests']!=[a['artifact_digest']] or b['raw_record_digests']!=[rec['raw_record_digest']] or b['coverage_event_digests']!=cds or b['cursor_digest']!=cur['cursor_digest'] or b['adapter_receipt_digest']!=rp['adapter_receipt_digest'] or b['transform_digest']!=ad['transform_digest']:return 'MSTA_P1A_E_RAW_NOT_IN_BUNDLE'
    disp=disposition(cs)
    if b['coverage_disposition']!=disp or ad['coverage_disposition']!=disp:return 'MSTA_P1A_E_SCHEMA_REJECT_CLEAR' if any(c['coverage_cause']=='SCHEMA_REJECT' for c in cs) else 'MSTA_P1A_E_COVERAGE_PROOF'
    if not (se['trusted_authority_snapshot_digest']==t['trusted_authority_snapshot_digest'] and all(se[k]==t[{'seal_authority_id':'authority_id','algorithm':'algorithm','key_id':'key_id','public_key_fingerprint':'public_key_fingerprint','verification_material_digest':'verification_material_digest','external_tip_contract_digest':'external_tip_contract_digest','external_tip_digest':'external_tip_digest'}[k]] for k in ('seal_authority_id','algorithm','key_id','public_key_fingerprint','verification_material_digest','external_tip_contract_digest','external_tip_digest')) and se['sealed_bundle_digest']==b['bundle_digest']==se['signed_payload_digest'] and se['seal_signature_digest']==sig(b['bundle_digest'],t['verification_material_digest'])):return 'MSTA_P1A_E_UNTRUSTED_FAKE_SEAL'
    try: expiry=utc(ad['decision_time'])<=utc(se['expires_at']) and utc(ad['decision_time'])<=utc(ad['expires_at'])<=utc(se['expires_at']) and utc(b['created_at'])<=utc(se['sealed_at'])<=utc(ad['decision_time'])
    except ValueError:expiry=False
    if not expiry:return 'MSTA_P1A_E_SEAL_EXPIRED'
    cp=v5['carrier_payload'];op=v5['result_payload']
    if v5['carrier_type'] not in E['v05_carriers'] or set(cp)!={'schema_version','carrier_id','available_at'} or set(op)!={'schema_version','result_id','decision_time'} or v5['carrier_digest']!=dh('msta/v05-carrier/v1',cp) or v5['result_digest']!=dh('msta/v05-result/v1',op) or ad['v05_binding_digest']!=v5['binding_digest']:return 'MSTA_P1A_E_V05_BINDING'
    if not(ad['logical_record_id']==rec['logical_record_id'] and ad['revision_id']==rec['revision_id'] and ad['raw_record_digest']==rec['raw_record_digest'] and ad['coverage_membership_digests']==cds and ad['bundle_digest']==b['bundle_digest'] and ad['seal_digest']==se['seal_digest'] and ad['expected_external_tip_digest']==se['external_tip_digest'] and ad['lane']==b['lane'] and ad['admission_status']=='ADMITTED' and not ad['reason_codes']):return 'MSTA_P1A_E_IDENTITY_DRIFT'
    return None

def mutate(x,case):
    if case=='INVALID_REVISION':x['rec']['revision_operation']='CANCEL';resign('RawRecordEnvelopeV1',x['rec'])
    elif case=='RECONSTRUCTED_ADMITTED':x['rec'].update(availability_kind='RECONSTRUCTED',counterfactual_available_at='2026-07-26T00:00:02Z',reconstruction_basis='replay');resign('RawRecordEnvelopeV1',x['rec'])
    elif case=='SCHEMA_REJECT_CLEAR':
     x['coverages'][0].update(coverage_state='OBSERVED_UNUSABLE',coverage_cause='SCHEMA_REJECT');resign('CoverageEventV1',x['coverages'][0]);cd=[x['coverages'][0]['coverage_event_digest']];x['rp']['coverage_event_digests']=cd;resign('AdapterReceiptV1',x['rp']);x['rs']['coverage_event_digests']=cd;x['rs']['receipt_digest']=x['rp']['adapter_receipt_digest'];resign('AdapterResultV1',x['rs']);x['bun']['coverage_event_digests']=cd;x['bun']['adapter_receipt_digest']=x['rp']['adapter_receipt_digest'];resign('RawAuthorityBundleManifestV1',x['bun'])
    elif case=='RAW_NOT_IN_BUNDLE':x['bun']['raw_record_digests']=['f'*64];resign('RawAuthorityBundleManifestV1',x['bun'])
    elif case=='UNTRUSTED_FAKE_SEAL':x['seal']['key_id']='FAKE';resign('RawAuthoritySealV1',x['seal'])
    elif case=='CONTRACT_DIGEST':x['bun']['p1a_contract_digest']='0'*64;resign('RawAuthorityBundleManifestV1',x['bun'])
    elif case=='REQUEST_SOURCE_DRIFT':x['req']['source_snapshot_digest']='0'*64;resign('AdapterRequestV1',x['req'])
    elif case=='CLASS_DRIFT':x['rs']['result_class']='REJECTED_PERMANENT';resign('AdapterResultV1',x['rs'])
    elif case=='CURSOR_DRIFT':x['rp']['next_cursor_digest']='0'*64;resign('AdapterReceiptV1',x['rp'])
    elif case=='NO_ACTIVITY_PROOF':x['coverages'][0].update(coverage_state='CONFIRMED_NO_ACTIVITY',proof_kind='NONE');resign('CoverageEventV1',x['coverages'][0])
    elif case=='REVERSED_INTERVAL':x['coverages'][0].update(interval_start='2026-07-26T00:00:02Z');resign('CoverageEventV1',x['coverages'][0])
    elif case=='V05_ARBITRARY':x['v5']['carrier_digest']='0'*64;resign('V05CarrierBindingV1',x['v5'])
    elif case=='MISSING_PREFIX':x['req'].pop('expected_prefix_digest')
    elif case=='PATH':x['art']['logical_path']='raw/%2e%2e/x';resign('RawArtifactDescriptorV1',x['art'])
    elif case=='ACTIVE':x['bun']['plan_id']='ACTIVE_G1';resign('RawAuthorityBundleManifestV1',x['bun'])
    elif case=='FORK_DRIFT':x['rec']['revision_fork_id']='FORK-OTHER';resign('RawRecordEnvelopeV1',x['rec'])
    elif case=='GEN_UNKNOWN':x['coverages'][0]['generation_boundary']=True;resign('CoverageEventV1',x['coverages'][0])
    elif case=='CAUSE_CLEAR':
     x['coverages'][0]['coverage_cause']='RATE_LIMIT';resign('CoverageEventV1',x['coverages'][0]);cd=[x['coverages'][0]['coverage_event_digest']];x['rp']['coverage_event_digests']=cd;resign('AdapterReceiptV1',x['rp']);x['rs']['coverage_event_digests']=cd;x['rs']['receipt_digest']=x['rp']['adapter_receipt_digest'];resign('AdapterResultV1',x['rs']);x['bun']['coverage_event_digests']=cd;x['bun']['adapter_receipt_digest']=x['rp']['adapter_receipt_digest'];resign('RawAuthorityBundleManifestV1',x['bun'])
    elif case=='CURSOR_ORPHAN':x['cur']['cursor_ordinal']=999;resign('AdapterCursorV1',x['cur'])
    elif case=='FUTURE_ARTIFACT':x['art']['captured_at']='2026-07-27T00:00:00Z';resign('RawArtifactDescriptorV1',x['art']);x['rec']['artifact_digest']=x['art']['artifact_digest'];resign('RawRecordEnvelopeV1',x['rec'])
    elif case=='FUTURE_REQUEST':x['req']['decision_time']='2026-07-27T00:00:00Z';resign('AdapterRequestV1',x['req'])
    elif case=='FAKE_TIP':x['seal']['external_tip_digest']='0'*64;resign('RawAuthoritySealV1',x['seal'])
    elif case=='EMPTY_RECEIPT':x['rs']['result_class']='EMPTY';resign('AdapterResultV1',x['rs'])
    elif case=='PAYLOAD_LENGTH_MISSING':x['req'].pop('supplied_payload_byte_length')
    elif case=='ACTIVE_CURSOR':x['cur']['cursor_token']='Application%20Support';resign('AdapterCursorV1',x['cur'])
    elif case=='EXPIRED_SEAL':x['seal']['expires_at']='2026-07-26T00:00:02Z';resign('RawAuthoritySealV1',x['seal'])

class R2(unittest.TestCase):
 def test_happy(self):self.assertIsNone(validate({**bind(),'coverages':[bind()['cov']]}))
 def test_fixture_cases_execute(self):
  expected={c['mutator']:c['expected_reason'] for c in FIXTURE['counterexamples']}
  self.assertEqual(set(expected),set(FIXTURE['executed_mutators']))
  for m,want in expected.items():
   x=bind();x['coverages']=[x['cov']];mutate(x,m);self.assertEqual(validate(x),want,m)
 def test_schema_paths_and_trust_are_real_inputs(self):
  x=bind();x['coverages']=[x['cov']];self.assertEqual(schema('RawArtifactDescriptorV1',x['art']),None)
  for bad in ('/a','../a','a//b','a/./b','a\\b','C:a','a/%2e','~/a'):
   y=copy.deepcopy(x);y['art']['logical_path']=bad;resign('RawArtifactDescriptorV1',y['art']);self.assertEqual(validate(y),'MSTA_P1A_E_PATH_INVALID')
  y=copy.deepcopy(x);y['trust'].pop('key_id');self.assertEqual(validate(y),'MSTA_P1A_E_SCHEMA_EXACT')
 def test_coverage_multiple_members_and_proofs(self):
  x=bind();extra=copy.deepcopy(x['cov']);extra['coverage_event_id']='COV-2';extra.update(coverage_state='CONFIRMED_NO_ACTIVITY',proof_kind='NO_ACTIVITY_SOURCE_PROOF',proof_ref='proof-2',proof_digest='9'*64);resign('CoverageEventV1',extra);x['coverages']=[x['cov'],extra]
  x['rp']['coverage_event_digests']=[x['cov']['coverage_event_digest'],extra['coverage_event_digest']];resign('AdapterReceiptV1',x['rp']);x['rs']['coverage_event_digests']=x['rp']['coverage_event_digests'];x['rs']['receipt_digest']=x['rp']['adapter_receipt_digest'];resign('AdapterResultV1',x['rs']);x['bun']['coverage_event_digests']=x['rp']['coverage_event_digests'];x['bun']['adapter_receipt_digest']=x['rp']['adapter_receipt_digest'];resign('RawAuthorityBundleManifestV1',x['bun']);x['ad']['coverage_membership_digests']=x['bun']['coverage_event_digests'];x['ad']['bundle_digest']=x['bun']['bundle_digest'];resign('EvidenceAdmissionContextV1',x['ad'])
  self.assertEqual(validate(x),'MSTA_P1A_E_UNTRUSTED_FAKE_SEAL')
 def test_contract_boundary(self):
  cc=dict(CONTRACT);cc.pop('contract_sha256');ff=dict(FIXTURE);ff.pop('fixture_sha256');self.assertEqual(CONTRACT['contract_sha256'],dh('msta-hed/raw-authority-bundle-contract/v1',cc));self.assertEqual(FIXTURE['fixture_sha256'],dh('msta-hed/raw-authority-bundle-synthetic-fixture/v1',ff));self.assertFalse(CONTRACT['implementation_authorized'] or CONTRACT['io_authorized']);self.assertEqual(len(CONTRACT['closed_enums']['coverage_states']),9);self.assertEqual(CONTRACT['theory_test_plan']['market_path_order'],['H01','H03','H05','H02','H04','H06','H08','H07'])
