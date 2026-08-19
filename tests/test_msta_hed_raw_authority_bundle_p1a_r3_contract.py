from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from trade_system.msta_hed_raw_authority_bundle_p1a_reference_v0_1_3 import _hash, validate_p1a_r3

ROOT=Path(__file__).resolve().parents[1]
C=json.loads((ROOT/'config/msta_hed_raw_authority_bundle.p1a_contract.v0_1_3.json').read_text())
F=json.loads((ROOT/'config/msta_hed_raw_authority_bundle.p1a_synthetic_contract.v0_1_3.json').read_text())
S=C['schemas']
def sign(n,v):
 o=dict(v);o[S[n]['digest_field']]=_hash(S[n]['domain'],o);return o
def resign(n,o):o[S[n]['digest_field']]=_hash(S[n]['domain'],{k:v for k,v in o.items() if k!=S[n]['digest_field']})
def make(empty=False,no_activity=False):
 tr=sign('TransformAuthorityV1',{'schema_type':'TransformAuthorityV1','transform_id':'SYNTHETIC-TRANSFORM-1','transform_digest':'1'*64,'authorized':True})
 pr=sign('CoverageProofV1',{'schema_type':'CoverageProofV1','proof_kind':'NO_ACTIVITY_AUTHORITY_BOUND' if no_activity else 'CONTINUOUS_OBSERVED','proof_ref':'proof-1','proof_digest':'2'*64,'coverage_disposition':'CLEAR'})
 tip=sign('ExternalTipCommitmentV1',{'schema_type':'ExternalTipCommitmentV1','tip_id':'SYNTHETIC-TIP-1','tip_digest':'3'*64,'committed_at':'2026-07-26T00:00:01Z'})
 ev={'evidence_id':'E-1','available_at':'2026-07-26T00:00:01Z','perspective_id':'PERSPECTIVE-SYNTHETIC-E0','dependency_group':'DEPENDENCY-V5M00-1','target_ids':['H01'],'direction':'SUPPORT','ordinal_strength':'WEAK','quality':'VALID','source_version':'SYNTHETIC-SOURCE-V1'}
 v5=sign('ExactV05EvidenceBindingV1',{'schema_type':'ExactV05EvidenceBindingV1','evidence':ev,'method_contract_physical_sha256':'18ef5234cb018d1a89252733a6d66903a145864031a2c8d663f021abe79740b0','method_contract_canonical_sha256':'39b9044cd172d239ab3d81a990bbe787035fbe618f6cc500274dcf2e93e067fd'})
 rec=sign('RawRecordEnvelopeV1',{'schema_type':'RawRecordEnvelopeV1','raw_record_id':'RAW-1','logical_record_id':'LOG-1','revision_id':'REV-1','revision_operation':'INITIAL','predecessor_revision_id':None,'revision_ordinal':0,'event_at':'2026-07-26T00:00:01Z','available_at':'2026-07-26T00:00:01Z','payload_sha256':'4'*64})
 values={'schema_type':'ValidatorInputV1','lane':'SYNTHETIC_CONTRACT','capability':'SUPPLIED_PAYLOAD_ONLY','payload_sha256':'5'*64,'payload_byte_length':0 if empty else 1,'decision_time':'2026-07-26T00:00:02Z','prior_cursor_digest':None,'previous_receipt_digest':None,'expected_prefix_digest':None,'trust_root_id':'PINNED-SYNTHETIC-TRUST-ROOT-1','records':[] if empty else [rec],'transform_authority':None if empty else tr,'coverage_proof':None if empty else pr,'external_tip':None if empty else tip,'v05_binding':None if empty else v5,'receipt':None if empty else {'receipt_id':'R-1','result_class':'ACCEPTED'},'admission':None if empty else {'admission_id':'A-1','status':'ADMITTED'}}
 return {'input':sign('ValidatorInputV1',values)}
def mutate(x,m):
 aliases={'FIELD_INPUT':'FIELD','FIELD_RECORD':'FIELD','V05_MISSING':'V05','V05_EXTRA':'V05','R2_INVALID_REVISION':'NONINITIAL','R2_RECONSTRUCTED_ADMITTED':'FIELD','R2_SCHEMA_REJECT_CLEAR':'COVERAGE','R2_RAW_NOT_IN_BUNDLE':'SECOND','R2_UNTRUSTED_FAKE_SEAL':'ROOT','R2_REQUEST_SOURCE_DRIFT':'FIELD','R2_CLASS_DRIFT':'RESULT','R2_CURSOR_DRIFT':'CURSOR','R2_NO_ACTIVITY_PROOF':'PROOF','R2_REVERSED_INTERVAL':'CLOCK','R2_V05_ARBITRARY':'V05','R2_MISSING_PREFIX':'PREFIX','R2_PATH':'ACTIVE','R2_ACTIVE':'ACTIVE','R2_FORK_DRIFT':'NONINITIAL','R2_GEN_UNKNOWN':'COVERAGE','R2_CAUSE_CLEAR':'COVERAGE','R2_CURSOR_ORPHAN':'CURSOR','R2_FUTURE_ARTIFACT':'CLOCK','R2_FUTURE_REQUEST':'CLOCK','R2_FAKE_TIP':'TIP','R2_EMPTY_RECEIPT':'EMPTY_RECEIPT','R2_PAYLOAD_LENGTH_MISSING':'FIELD','R2_ACTIVE_CURSOR':'ACTIVE','R2_EXPIRED_SEAL':'CLOCK'}
 m=aliases.get(m,m)
 i=x['input']
 if m=='LANE':i['lane']='DEVELOPMENT'
 elif m=='TRANSFORM':i['transform_authority']['authorized']=False;resign('TransformAuthorityV1',i['transform_authority'])
 elif m=='CAPABILITY':i['capability']='NETWORK'
 elif m=='RESULT':i['receipt']['result_class']='REJECTED'
 elif m=='FIELD':i['payload_byte_length']=True
 elif m=='COVERAGE':i['coverage_proof']['coverage_disposition']='UNKNOWN';resign('CoverageProofV1',i['coverage_proof'])
 elif m=='PROOF':i['coverage_proof']['proof_kind']='OTHER';resign('CoverageProofV1',i['coverage_proof'])
 elif m=='PREFIX':i['expected_prefix_digest']='0'*64
 elif m=='CURSOR':i['prior_cursor_digest']='0'*64
 elif m=='ROOT':i['trust_root_id']='CANDIDATE-ROOT'
 elif m=='V05':i['v05_binding']['evidence'].pop('ordinal_strength');resign('ExactV05EvidenceBindingV1',i['v05_binding'])
 elif m=='TIP':i['external_tip']['tip_id']='OTHER';resign('ExternalTipCommitmentV1',i['external_tip'])
 elif m=='CLOCK':i['decision_time']='2027-01-01T00:00:00Z'
 elif m=='NONINITIAL':i['records'][0]['revision_operation']='CORRECT';resign('RawRecordEnvelopeV1',i['records'][0])
 elif m=='SECOND':i['records'].append(copy.deepcopy(i['records'][0]))
 elif m=='EMPTY_RECEIPT':return make(empty=True)|{'input':dict(make(empty=True)['input'],receipt={'receipt_id':'X','result_class':'ACCEPTED'})}
 elif m=='NONEMPTY_RECEIPT':i['receipt']=None
 elif m=='ACTIVE':i['records'][0]['raw_record_id']='ACTIVE_G1';resign('RawRecordEnvelopeV1',i['records'][0])
 elif m=='CONTRACT':return x
 resign('ValidatorInputV1',i);return x

class P1AR3(unittest.TestCase):
 def test_three_positive_cases(self):
  self.assertEqual(validate_p1a_r3(C,make())['status'],'ADMITTED')
  z=validate_p1a_r3(C,make(empty=True));self.assertEqual((z['status'],z['receipt'],z['admission']),('VALID_EMPTY_NOT_ADMITTED',None,None))
  self.assertEqual(validate_p1a_r3(C,make(no_activity=True))['status'],'ADMITTED')
 def test_fixture_mutators_call_module(self):
  for m,want in F['mutator_cases']:
   x=make()
   if m in ('CONTRACT_REWRITE','R2_CONTRACT_DIGEST'):
    bad=copy.deepcopy(C);bad['scope']['allowed_lane']='REWRITTEN';bad.pop('contract_sha256');bad['contract_sha256']=_hash('msta-hed/raw-authority-bundle-contract/v1',bad);got=validate_p1a_r3(bad,x)
   elif m in ('EMPTY_RECEIPT','R2_EMPTY_RECEIPT'):
    x=make(empty=True);x['input']['receipt']={'receipt_id':'X','result_class':'ACCEPTED'};resign('ValidatorInputV1',x['input']);got=validate_p1a_r3(C,x)
   elif m=='ROOT_INJECTION':
    x['pinned_root']={'trust_root_id':'PINNED-SYNTHETIC-TRUST-ROOT-1'};got=validate_p1a_r3(C,x)
   else: got=validate_p1a_r3(C,mutate(x,m))
   self.assertEqual(got['reason_code'],want,m)
  self.assertEqual(len(F['mutator_cases']),48)
 def test_candidate_cannot_inject_pinned_root(self):
  x=make();x['pinned_root']={'trust_root_id':'PINNED-SYNTHETIC-TRUST-ROOT-1'}
  self.assertEqual(validate_p1a_r3(C,x)['reason_code'],'E_TRUST_ROOT_MISMATCH')
 def test_exact_v05_evidence_nine_fields(self):
  x=make();self.assertEqual(set(x['input']['v05_binding']['evidence']),{'evidence_id','available_at','perspective_id','dependency_group','target_ids','direction','ordinal_strength','quality','source_version'})
  x['input']['v05_binding']['evidence']['ordinal_strength']=1;resign('ExactV05EvidenceBindingV1',x['input']['v05_binding']);resign('ValidatorInputV1',x['input'])
  self.assertEqual(validate_p1a_r3(C,x)['reason_code'],'E_V05_CARRIER_NOT_SUPPORTED_P1A')
