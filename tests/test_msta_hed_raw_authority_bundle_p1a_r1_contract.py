"""P1A-R1 static executable reference validation; never a source adapter or data reader."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/msta_hed_raw_authority_bundle.p1a_contract.v0_1_1.json"
FIXTURE_PATH = ROOT / "config/msta_hed_raw_authority_bundle.p1a_synthetic_contract.v0_1_1.json"
SPEC_PATH = ROOT / "archive/authority/MSTA_HED_RAW_AUTHORITY_BUNDLE_P1A_SPEC_v0_1_1.md"


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MSTA_P1A_E_SCHEMA_EXACT")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)


CONTRACT = _load(CONTRACT_PATH)
FIXTURE = _load(FIXTURE_PATH)
SCHEMAS = CONTRACT["object_schemas"]
ENUMS = CONTRACT["closed_enums"]
TRUSTED_SNAPSHOT = "a" * 64
TRUSTED_AUTHORITY = "TEST-TRUSTED-SEALER-1"
TRUSTED_FINGERPRINT = "b" * 64
TRUSTED_MATERIAL = "c" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(domain: str, value: object) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\x00" + _canonical(value)).hexdigest()


def _digest(schema_name: str, obj: dict[str, object]) -> str:
    field = SCHEMAS[schema_name]["digest_field"]
    payload = dict(obj)
    payload.pop(field, None)
    return _sha(SCHEMAS[schema_name]["domain"], payload)


def _utc(value: object) -> datetime:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise ValueError("MSTA_P1A_E_SCHEMA_EXACT")
    return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)


def _safe_path(value: object) -> bool:
    return type(value) is str and bool(value) and not value.startswith("/") and "\\" not in value and "%" not in value and "~" not in value and not re.match(r"^[A-Za-z]:", value) and all(p not in ("", ".", "..") for p in value.split("/"))


def _matches(value: object, definition: object) -> bool:
    if type(definition) is str:
        if definition == "null":
            return value is None
        definition = CONTRACT["field_type_definitions"][definition]
    assert type(definition) is dict
    if "any_of" in definition:
        return any(_matches(value, item) for item in definition["any_of"])
    if "const" in definition:
        return value == definition["const"] and type(value) is type(definition["const"])
    if "enum_ref" in definition:
        return type(value) is str and value in ENUMS[definition["enum_ref"]]
    if "enum" in definition:
        return value in definition["enum"] and type(value) is str
    if definition.get("type") == "null":
        return value is None
    if definition.get("type") == "boolean":
        return type(value) is bool
    if definition.get("type") == "integer":
        return type(value) is int and not isinstance(value, bool) and value >= definition.get("minimum", 0)
    if definition.get("type") == "array":
        if type(value) is not list or (definition.get("unique") and len(value) != len(set(value))):
            return False
        return all(_matches(item, definition["items"]) for item in value)
    if definition.get("type") != "string" or type(value) is not str:
        return False
    if len(value) < definition.get("min_length", 0):
        return False
    if definition.get("pattern") and not re.fullmatch(definition["pattern"], value):
        return False
    if definition.get("format") == "UTC_Z_SECONDS":
        try:
            _utc(value)
        except ValueError:
            return False
    if definition.get("format") == "SAFE_RELATIVE_PATH" and not _safe_path(value):
        return False
    return True


def _validate_schema(name: str, obj: object) -> str | None:
    spec = SCHEMAS.get(name)
    if spec is None or type(obj) is not dict or set(obj) != set(spec["exact_fields"]):
        return "MSTA_P1A_E_SCHEMA_EXACT"
    for field, definition in spec["field_types"].items():
        if not _matches(obj[field], definition):
            return "MSTA_P1A_E_SCHEMA_EXACT"
    if obj[spec["digest_field"]] != _digest(name, obj):
        return "MSTA_P1A_E_DIGEST_INVALID"
    return None


def _sign(name: str, values: dict[str, object]) -> dict[str, object]:
    spec = SCHEMAS[name]
    if set(values) != set(spec["exact_fields"]) - {spec["digest_field"]}:
        raise AssertionError(name)
    obj = dict(values)
    obj[spec["digest_field"]] = _digest(name, obj)
    return obj


def _coverage_disposition(events: list[dict[str, object]]) -> str:
    if not events:
        return "UNKNOWN"
    clear = {"CONTINUOUS_OBSERVED", "CONFIRMED_NO_ACTIVITY", "EXPECTED_SNAPSHOT_CADENCE", "MARKET_HALT"}
    if any(event["coverage_cause_code"] == "SCHEMA_REJECT" for event in events):
        return "BLOCKED"
    if all(event["coverage_state"] in clear for event in events):
        return "CLEAR"
    if any(event["coverage_state"] == "UNKNOWN_COVERAGE" for event in events):
        return "UNKNOWN"
    return "BLOCKED"


def _idempotency(request: dict[str, object]) -> str:
    fields = [request["adapter_contract_digest"], request["source_snapshot_digest"], request["prior_cursor_digest"] or "NULL", request["supplied_payload_sha256"], request["decision_time"]]
    return hashlib.sha256("|".join(fields).encode("ascii")).hexdigest()


def _seal_signature(bundle_digest: str) -> str:
    return hashlib.sha256(b"test-seal\x00" + bundle_digest.encode("ascii") + TRUSTED_MATERIAL.encode("ascii")).hexdigest()


def _lineage_reason(records: list[dict[str, object]], coverage: list[dict[str, object]]) -> str | None:
    generations = {c["source_generation_id"] for c in coverage if c["generation_boundary"]}
    by_logical: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_logical.setdefault(record["logical_record_id"], []).append(record)
    for lineage in by_logical.values():
        lineage.sort(key=lambda x: x["revision_ordinal"])
        seen: set[str] = set()
        for ordinal, record in enumerate(lineage):
            if len({record["raw_record_id"], record["logical_record_id"], record["revision_id"]}) != 3:
                return "MSTA_P1A_E_INVALID_REVISION"
            if record["revision_id"] in seen or record["revision_ordinal"] != ordinal:
                return "MSTA_P1A_E_INVALID_REVISION"
            seen.add(record["revision_id"])
            if ordinal == 0:
                if record["revision_operation"] != "INITIAL" or record["predecessor_revision_id"] is not None:
                    return "MSTA_P1A_E_INVALID_REVISION"
            elif record["predecessor_revision_id"] != lineage[ordinal - 1]["revision_id"]:
                return "MSTA_P1A_E_INVALID_REVISION"
            if record["source_generation_id"] != lineage[0]["source_generation_id"] and record["source_generation_id"] not in generations:
                return "MSTA_P1A_E_INVALID_REVISION"
            expected_state = "TOMBSTONE" if record["revision_operation"] in ("CANCEL", "REORG_RETRACT") else "ACTIVE"
            if record["record_state"] != expected_state:
                return "MSTA_P1A_E_INVALID_REVISION"
    return None


def _record_reason(record: dict[str, object], decision_time: str) -> str | None:
    base = _validate_schema("RawRecordEnvelopeV1", record)
    if base:
        return base
    try:
        received, ingested, derived, actual, decision = [_utc(record[k]) for k in ("received_at", "ingested_at", "derived_at", "actual_available_at")] + [_utc(decision_time)]
        optional = [_utc(record[k]) for k in ("event_at", "published_at") if record[k] is not None]
    except ValueError:
        return "MSTA_P1A_E_PIT_ORDER"
    if not received <= ingested <= derived <= actual <= decision or any(v > actual for v in optional):
        return "MSTA_P1A_E_PIT_ORDER"
    actual_kind = record["availability_kind"] == "ACTUAL"
    reconstructed_ok = record["counterfactual_available_at"] is not None and record["reconstruction_basis"] is not None
    if (actual_kind and (record["counterfactual_available_at"] is not None or record["reconstruction_basis"] is not None)) or (not actual_kind and not reconstructed_ok):
        return "MSTA_P1A_E_PIT_ORDER"
    return None


def _chain() -> dict[str, object]:
    source = _sign("SourceAuthoritySnapshotV1", {"schema_type": "SourceAuthoritySnapshotV1", "source_snapshot_id": "SRC-1", "source_id": "S-1", "source_generation_id": "GEN-1", "source_contract_digest": "1" * 64, "adapter_contract_digest": "2" * 64, "capabilities": ["SUPPLIED_PAYLOAD_ONLY"], "coverage_semantics": "OBSERVED_ONLY", "frozen_at": "2026-07-26T00:00:00Z"})
    artifact = _sign("RawArtifactDescriptorV1", {"schema_type": "RawArtifactDescriptorV1", "artifact_id": "ART-1", "source_snapshot_digest": source["source_snapshot_digest"], "logical_path": "raw/p1a/part.ndjson", "content_sha256": "3" * 64, "byte_length": 1, "media_type": "application/x-ndjson", "captured_at": "2026-07-26T00:00:01Z"})
    record = _sign("RawRecordEnvelopeV1", {"schema_type": "RawRecordEnvelopeV1", "raw_record_id": "RAW-1", "logical_record_id": "LOG-1", "revision_id": "REV-1", "revision_operation": "INITIAL", "predecessor_revision_id": None, "revision_ordinal": 0, "revision_fork_id": "FORK-1", "source_generation_id": "GEN-1", "artifact_digest": artifact["artifact_digest"], "record_locator": "line-1", "event_at": "2026-07-26T00:00:00Z", "published_at": None, "received_at": "2026-07-26T00:00:01Z", "ingested_at": "2026-07-26T00:00:01Z", "derived_at": "2026-07-26T00:00:01Z", "actual_available_at": "2026-07-26T00:00:01Z", "availability_kind": "ACTUAL", "counterfactual_available_at": None, "reconstruction_basis": None, "payload_sha256": "4" * 64, "record_state": "ACTIVE"})
    coverage = _sign("CoverageEventV1", {"schema_type": "CoverageEventV1", "coverage_event_id": "COV-1", "source_snapshot_digest": source["source_snapshot_digest"], "source_generation_id": "GEN-1", "coverage_state": "CONTINUOUS_OBSERVED", "coverage_cause_code": "NONE", "affected_scope": "S-1-metadata", "interval_start": "2026-07-26T00:00:00Z", "interval_end": "2026-07-26T00:00:01Z", "observed_at": "2026-07-26T00:00:01Z", "generation_boundary": False})
    cursor = _sign("AdapterCursorV1", {"schema_type": "AdapterCursorV1", "cursor_id": "CUR-1", "source_snapshot_digest": source["source_snapshot_digest"], "source_generation_id": "GEN-1", "stream_scope": "S-1-metadata", "cursor_token": "token-1", "cursor_ordinal": 1, "observed_at": "2026-07-26T00:00:01Z", "predecessor_cursor_digest": None})
    request_values = {"schema_type": "AdapterRequestV1", "request_id": "REQ-1", "source_snapshot_digest": source["source_snapshot_digest"], "adapter_contract_digest": source["adapter_contract_digest"], "prior_cursor_digest": None, "supplied_payload_sha256": "5" * 64, "decision_time": "2026-07-26T00:00:02Z", "idempotency_key": "0" * 64, "capabilities": ["SUPPLIED_PAYLOAD_ONLY"]}
    request_values["idempotency_key"] = _idempotency(request_values)
    request = _sign("AdapterRequestV1", request_values)
    receipt = _sign("AdapterReceiptV1", {"schema_type": "AdapterReceiptV1", "adapter_receipt_id": "REC-1", "request_digest": request["adapter_request_digest"], "prior_cursor_digest": None, "next_cursor_digest": cursor["cursor_digest"], "input_payload_sha256": request["supplied_payload_sha256"], "result_class": "ACCEPTED", "reason_codes": [], "record_digests": [record["raw_record_digest"]], "coverage_event_digests": [coverage["coverage_event_digest"]], "idempotency_key": request["idempotency_key"]})
    result = _sign("AdapterResultV1", {"schema_type": "AdapterResultV1", "request_digest": request["adapter_request_digest"], "receipt_digest": receipt["adapter_receipt_digest"], "next_cursor_digest": cursor["cursor_digest"], "record_digests": [record["raw_record_digest"]], "coverage_event_digests": [coverage["coverage_event_digest"]], "result_class": "ACCEPTED", "reason_codes": []})
    bundle = _sign("RawAuthorityBundleManifestV1", {"schema_type": "RawAuthorityBundleManifestV1", "bundle_id": "BUNDLE-1", "lane": "SYNTHETIC_CONTRACT", "plan_id": "PLAN-1", "registry_digest": "6" * 64, "evidence_root_id": "ROOT-1", "p1a_contract_digest": CONTRACT["contract_sha256"], "source_snapshot_digest": source["source_snapshot_digest"], "adapter_contract_digest": source["adapter_contract_digest"], "transform_digest": "7" * 64, "artifact_digests": [artifact["artifact_digest"]], "raw_record_digests": [record["raw_record_digest"]], "coverage_event_digests": [coverage["coverage_event_digest"]], "cursor_digest": cursor["cursor_digest"], "adapter_receipt_digest": receipt["adapter_receipt_digest"], "coverage_disposition": "CLEAR", "created_at": "2026-07-26T00:00:02Z"})
    seal = _sign("RawAuthoritySealV1", {"schema_type": "RawAuthoritySealV1", "seal_id": "SEAL-1", "trusted_authority_snapshot_digest": TRUSTED_SNAPSHOT, "seal_authority_id": TRUSTED_AUTHORITY, "algorithm": "TEST_DETERMINISTIC_SHA256", "key_id": "KEY-1", "public_key_fingerprint": TRUSTED_FINGERPRINT, "verification_material_digest": TRUSTED_MATERIAL, "sealed_bundle_digest": bundle["bundle_digest"], "signed_payload_digest": bundle["bundle_digest"], "external_tip_contract_digest": "8" * 64, "external_tip_id": "TIP-1", "external_tip_digest": "9" * 64, "sealed_at": "2026-07-26T00:00:02Z", "expires_at": "2026-07-27T00:00:02Z", "seal_signature_digest": _seal_signature(bundle["bundle_digest"])})
    admission = _sign("EvidenceAdmissionContextV1", {"schema_type": "EvidenceAdmissionContextV1", "admission_context_id": "ADM-1", "v0_5_carrier_type": "Evidence", "v0_5_carrier_digest": "d" * 64, "v0_5_result_digest": "e" * 64, "raw_record_digest": record["raw_record_digest"], "logical_record_id": record["logical_record_id"], "revision_id": record["revision_id"], "transform_digest": bundle["transform_digest"], "coverage_membership_digests": [coverage["coverage_event_digest"]], "coverage_disposition": "CLEAR", "bundle_digest": bundle["bundle_digest"], "seal_digest": seal["seal_digest"], "expected_external_tip_digest": seal["external_tip_digest"], "expires_at": seal["expires_at"], "decision_time": "2026-07-26T00:00:03Z", "lane": "SYNTHETIC_CONTRACT", "admission_status": "ADMITTED", "reason_codes": []})
    return locals()


def _admission_reason(chain: dict[str, object]) -> str | None:
    for name in ("source", "artifact", "record", "coverage", "cursor", "request", "receipt", "result", "bundle", "seal", "admission"):
        schema = {"source": "SourceAuthoritySnapshotV1", "artifact": "RawArtifactDescriptorV1", "record": "RawRecordEnvelopeV1", "coverage": "CoverageEventV1", "cursor": "AdapterCursorV1", "request": "AdapterRequestV1", "receipt": "AdapterReceiptV1", "result": "AdapterResultV1", "bundle": "RawAuthorityBundleManifestV1", "seal": "RawAuthoritySealV1", "admission": "EvidenceAdmissionContextV1"}[name]
        reason = _validate_schema(schema, chain[name])
        if reason:
            return reason
    source, artifact, record, coverage, cursor, request, receipt, result, bundle, seal, admission = [chain[k] for k in ("source", "artifact", "record", "coverage", "cursor", "request", "receipt", "result", "bundle", "seal", "admission")]
    identifiers = [source["source_id"], source["source_generation_id"], artifact["logical_path"], record["logical_record_id"], bundle["plan_id"], bundle["evidence_root_id"], admission["admission_context_id"]]
    if any("ACTIVE_G1" in value.upper() or "APPLICATION SUPPORT" in value.upper() or "APPLICATION_SUPPORT" in value.upper() for value in identifiers):
        return "MSTA_P1A_E_ACTIVE_G1_FORBIDDEN"
    if _record_reason(record, admission["decision_time"]):
        return _record_reason(record, admission["decision_time"])
    if _lineage_reason([record], [coverage]):
        return _lineage_reason([record], [coverage])
    if request["idempotency_key"] != _idempotency(request) or receipt["idempotency_key"] != request["idempotency_key"]:
        return "MSTA_P1A_E_IDEMPOTENCY_FORMULA"
    if request["capabilities"] != ["SUPPLIED_PAYLOAD_ONLY"]:
        return "MSTA_P1A_E_CAPABILITY_NOT_ALLOWLISTED"
    if result["request_digest"] != request["adapter_request_digest"] or result["receipt_digest"] != receipt["adapter_receipt_digest"]:
        return "MSTA_P1A_E_ADAPTER_SCHEMA_MISSING"
    if result["result_class"] != "EMPTY" and result["receipt_digest"] is None:
        return "MSTA_P1A_E_ADAPTER_SCHEMA_MISSING"
    if receipt["result_class"] != "EMPTY" and not receipt["adapter_receipt_id"]:
        return "MSTA_P1A_E_ADAPTER_SCHEMA_MISSING"
    if receipt["record_digests"] != [record["raw_record_digest"]] or receipt["coverage_event_digests"] != [coverage["coverage_event_digest"]] or result["record_digests"] != receipt["record_digests"] or result["coverage_event_digests"] != receipt["coverage_event_digests"]:
        return "MSTA_P1A_E_RAW_NOT_IN_BUNDLE"
    if _coverage_disposition([coverage]) != bundle["coverage_disposition"] or admission["coverage_disposition"] != bundle["coverage_disposition"]:
        return "MSTA_P1A_E_SCHEMA_REJECT_CLEAR" if coverage["coverage_cause_code"] == "SCHEMA_REJECT" else "MSTA_P1A_E_COVERAGE_UNKNOWN"
    if not (source["source_snapshot_digest"] == artifact["source_snapshot_digest"] == bundle["source_snapshot_digest"] and bundle["artifact_digests"] == [artifact["artifact_digest"]] and bundle["raw_record_digests"] == [record["raw_record_digest"]] and bundle["coverage_event_digests"] == [coverage["coverage_event_digest"]] and cursor["cursor_digest"] == bundle["cursor_digest"] and receipt["adapter_receipt_digest"] == bundle["adapter_receipt_digest"] and bundle["adapter_contract_digest"] == source["adapter_contract_digest"] and bundle["transform_digest"] == admission["transform_digest"]):
        return "MSTA_P1A_E_RAW_NOT_IN_BUNDLE"
    if not (seal["trusted_authority_snapshot_digest"] == TRUSTED_SNAPSHOT and seal["seal_authority_id"] == TRUSTED_AUTHORITY and seal["algorithm"] == "TEST_DETERMINISTIC_SHA256" and seal["public_key_fingerprint"] == TRUSTED_FINGERPRINT and seal["verification_material_digest"] == TRUSTED_MATERIAL and seal["sealed_bundle_digest"] == bundle["bundle_digest"] and seal["signed_payload_digest"] == bundle["bundle_digest"] and seal["seal_signature_digest"] == _seal_signature(bundle["bundle_digest"])):
        return "MSTA_P1A_E_UNTRUSTED_FAKE_SEAL"
    if record["availability_kind"] != "ACTUAL" and admission["admission_status"] == "ADMITTED":
        return "MSTA_P1A_E_RECONSTRUCTED_ADMITTED"
    if admission["lane"] not in ("SYNTHETIC_CONTRACT", "METADATA_ONLY", "DEVELOPMENT", "CALIBRATION", "ONE_SHOT_HOLDOUT", "PAPER_SHADOW") or admission["lane"] != bundle["lane"] or admission["admission_status"] != "ADMITTED" or admission["raw_record_digest"] != record["raw_record_digest"] or admission["coverage_membership_digests"] != bundle["coverage_event_digests"] or admission["bundle_digest"] != bundle["bundle_digest"] or admission["seal_digest"] != seal["seal_digest"] or admission["expected_external_tip_digest"] != seal["external_tip_digest"]:
        return "MSTA_P1A_E_RAW_NOT_IN_BUNDLE"
    if _utc(admission["decision_time"]) > _utc(admission["expires_at"]):
        return "MSTA_P1A_E_UNTRUSTED_FAKE_SEAL"
    if not (_utc(bundle["created_at"]) <= _utc(seal["sealed_at"]) <= _utc(admission["decision_time"])):
        return "MSTA_P1A_E_UNTRUSTED_FAKE_SEAL"
    if admission["reason_codes"]:
        return "MSTA_P1A_E_SCHEMA_EXACT"
    return None


def _resign(name: str, obj: dict[str, object]) -> None:
    obj[SCHEMAS[name]["digest_field"]] = _digest(name, obj)


class RawAuthorityBundleP1AR1ContractTests(unittest.TestCase):
    def test_contract_fixture_and_gate_are_static_only(self) -> None:
        self.assertTrue(SPEC_PATH.is_file())
        self.assertEqual(CONTRACT["status"], "DRAFT_AWAITING_SOL_P1A_R1_GATE")
        self.assertFalse(CONTRACT["implementation_authorized"] or CONTRACT["io_authorized"] or CONTRACT["market_or_outcome_access_authorized"])
        self.assertEqual(FIXTURE["lane"], "SYNTHETIC_CONTRACT")
        copy_contract = dict(CONTRACT); copy_contract.pop("contract_sha256")
        self.assertEqual(CONTRACT["contract_sha256"], _sha("msta-hed/raw-authority-bundle-contract/v1", copy_contract))
        copy_fixture = dict(FIXTURE); copy_fixture.pop("fixture_sha256")
        self.assertEqual(FIXTURE["fixture_sha256"], _sha("msta-hed/raw-authority-bundle-synthetic-fixture/v1", copy_fixture))

    def test_exact_schema_field_types_reject_x_and_extra(self) -> None:
        chain = _chain()
        for name, schema in SCHEMAS.items():
            self.assertEqual(set(schema["exact_fields"]), set(schema["field_types"]))
        candidate = copy.deepcopy(chain["record"]); candidate["raw_record_id"] = "x"; _resign("RawRecordEnvelopeV1", candidate)
        self.assertIsNone(_validate_schema("RawRecordEnvelopeV1", candidate))
        candidate["revision_ordinal"] = "x"; _resign("RawRecordEnvelopeV1", candidate)
        self.assertEqual(_validate_schema("RawRecordEnvelopeV1", candidate), "MSTA_P1A_E_SCHEMA_EXACT")
        candidate = copy.deepcopy(chain["artifact"]); candidate["extra"] = "x"
        self.assertEqual(_validate_schema("RawArtifactDescriptorV1", candidate), "MSTA_P1A_E_SCHEMA_EXACT")

    def test_duplicate_json_and_all_closed_enums(self) -> None:
        with self.assertRaisesRegex(ValueError, "MSTA_P1A_E_SCHEMA_EXACT"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=_pairs)
        self.assertEqual(len(ENUMS["coverage_states"]), 9)
        self.assertIn("SCHEMA_REJECT", ENUMS["coverage_cause_codes"])
        self.assertEqual(CONTRACT["interface_schemas"], ["AdapterRequestV1", "AdapterResultV1"])
        self.assertEqual(len(CONTRACT["authority_objects"]), 9)

    def test_happy_chain_admits_only_synthetic_actual(self) -> None:
        self.assertIsNone(_admission_reason(_chain()))

    def test_invalid_revision_counterexample_calls_validator(self) -> None:
        chain = _chain(); bad = chain["record"]; bad["revision_operation"] = "CORRECT"; _resign("RawRecordEnvelopeV1", bad)
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_INVALID_REVISION")

    def test_revisions_tombstones_fork_and_generation_boundary(self) -> None:
        chain = _chain(); initial = chain["record"]
        correction = copy.deepcopy(initial); correction.update({"raw_record_id": "RAW-2", "revision_id": "REV-2", "revision_operation": "CANCEL", "predecessor_revision_id": "REV-1", "revision_ordinal": 1, "record_state": "TOMBSTONE"}); _resign("RawRecordEnvelopeV1", correction)
        self.assertIsNone(_lineage_reason([initial, correction], [chain["coverage"]]))
        fork = copy.deepcopy(correction); fork["revision_ordinal"] = 2; fork["predecessor_revision_id"] = "REV-X"; _resign("RawRecordEnvelopeV1", fork)
        self.assertEqual(_lineage_reason([initial, correction, fork], [chain["coverage"]]), "MSTA_P1A_E_INVALID_REVISION")
        reset = copy.deepcopy(correction); reset.update({"revision_id": "REV-3", "revision_ordinal": 2, "predecessor_revision_id": "REV-2", "source_generation_id": "GEN-2", "revision_operation": "REINSTATE", "record_state": "ACTIVE"}); _resign("RawRecordEnvelopeV1", reset)
        self.assertEqual(_lineage_reason([initial, correction, reset], [chain["coverage"]]), "MSTA_P1A_E_INVALID_REVISION")
        boundary = copy.deepcopy(chain["coverage"]); boundary["source_generation_id"] = "GEN-2"; boundary["generation_boundary"] = True; _resign("CoverageEventV1", boundary)
        self.assertIsNone(_lineage_reason([initial, correction, reset], [chain["coverage"], boundary]))

    def test_pit_reconstructed_admission_counterexample_calls_validator(self) -> None:
        chain = _chain(); record = chain["record"]; record.update({"availability_kind": "RECONSTRUCTED", "counterfactual_available_at": "2026-07-26T00:00:02Z", "reconstruction_basis": "SYNTHETIC-REPLAY"}); _resign("RawRecordEnvelopeV1", record)
        chain["receipt"]["record_digests"] = [record["raw_record_digest"]]; _resign("AdapterReceiptV1", chain["receipt"])
        chain["result"]["record_digests"] = [record["raw_record_digest"]]; chain["result"]["receipt_digest"] = chain["receipt"]["adapter_receipt_digest"]; _resign("AdapterResultV1", chain["result"])
        chain["bundle"]["raw_record_digests"] = [record["raw_record_digest"]]; chain["bundle"]["adapter_receipt_digest"] = chain["receipt"]["adapter_receipt_digest"]; _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        chain["seal"]["sealed_bundle_digest"] = chain["bundle"]["bundle_digest"]; chain["seal"]["signed_payload_digest"] = chain["bundle"]["bundle_digest"]; chain["seal"]["seal_signature_digest"] = _seal_signature(chain["bundle"]["bundle_digest"]); _resign("RawAuthoritySealV1", chain["seal"])
        chain["admission"]["raw_record_digest"] = record["raw_record_digest"]; chain["admission"]["bundle_digest"] = chain["bundle"]["bundle_digest"]; chain["admission"]["seal_digest"] = chain["seal"]["seal_digest"]; _resign("EvidenceAdmissionContextV1", chain["admission"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_RECONSTRUCTED_ADMITTED")

    def test_schema_reject_clear_counterexample_calls_validator(self) -> None:
        chain = _chain(); coverage = chain["coverage"]; coverage.update({"coverage_state": "OBSERVED_UNUSABLE", "coverage_cause_code": "SCHEMA_REJECT"}); _resign("CoverageEventV1", coverage)
        chain["receipt"]["coverage_event_digests"] = [coverage["coverage_event_digest"]]; _resign("AdapterReceiptV1", chain["receipt"])
        chain["result"]["receipt_digest"] = chain["receipt"]["adapter_receipt_digest"]; chain["result"]["coverage_event_digests"] = [coverage["coverage_event_digest"]]; _resign("AdapterResultV1", chain["result"])
        chain["bundle"]["coverage_event_digests"] = [coverage["coverage_event_digest"]]; chain["bundle"]["adapter_receipt_digest"] = chain["receipt"]["adapter_receipt_digest"]; _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_SCHEMA_REJECT_CLEAR")

    def test_raw_not_in_bundle_counterexample_calls_validator(self) -> None:
        chain = _chain(); chain["bundle"]["raw_record_digests"] = ["f" * 64]; _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_RAW_NOT_IN_BUNDLE")

    def test_untrusted_fake_seal_counterexample_calls_validator(self) -> None:
        chain = _chain(); chain["seal"]["seal_authority_id"] = "BUNDLE-1"; _resign("RawAuthoritySealV1", chain["seal"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_UNTRUSTED_FAKE_SEAL")

    def test_missing_adapter_request_result_schema_counterexample_calls_validator(self) -> None:
        chain = _chain(); del chain["result"]["receipt_digest"]
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_SCHEMA_EXACT")
        self.assertIn("AdapterRequestV1", SCHEMAS); self.assertIn("AdapterResultV1", SCHEMAS)

    def test_missing_idempotency_formula_counterexample_calls_validator(self) -> None:
        chain = _chain(); chain["request"]["idempotency_key"] = "0" * 64; _resign("AdapterRequestV1", chain["request"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_IDEMPOTENCY_FORMULA")

    def test_nonempty_reject_requires_typed_receipt(self) -> None:
        chain = _chain(); chain["result"]["receipt_digest"] = None; chain["result"]["result_class"] = "REJECTED_PERMANENT"; _resign("AdapterResultV1", chain["result"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_ADAPTER_SCHEMA_MISSING")

    def test_no_io_capability_is_contractually_closed(self) -> None:
        self.assertIn("PURE_EXPLICIT_INPUTS_ONLY", CONTRACT["rules"]["adapter"])
        chain = _chain(); chain["request"]["capabilities"] = ["NETWORK"]; _resign("AdapterRequestV1", chain["request"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_SCHEMA_EXACT")

    def test_paths_and_digest_mutation_fail_closed(self) -> None:
        for bad in ("/raw/x", "../raw", "raw//x", "raw\\x", "C:raw", "raw/%2e%2e/x", "~/raw/x"):
            self.assertFalse(_safe_path(bad))
        chain = _chain(); chain["bundle"]["plan_id"] = "MUTATED"
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_DIGEST_INVALID")

    def test_membership_source_artifact_alias_clock_and_carrier_fail_closed(self) -> None:
        chain = _chain(); chain["bundle"]["raw_record_digests"].append("f" * 64); _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_RAW_NOT_IN_BUNDLE")
        chain = _chain(); chain["artifact"]["source_snapshot_digest"] = "f" * 64; _resign("RawArtifactDescriptorV1", chain["artifact"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_RAW_NOT_IN_BUNDLE")
        chain = _chain(); chain["bundle"]["created_at"] = "2026-07-27T00:00:03Z"; _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_UNTRUSTED_FAKE_SEAL")
        chain = _chain(); chain["admission"]["v0_5_carrier_type"] = "Other"; _resign("EvidenceAdmissionContextV1", chain["admission"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_SCHEMA_EXACT")

    def test_active_g1_alias_and_admitted_error_list_fail_closed(self) -> None:
        chain = _chain(); chain["bundle"]["lane"] = "DEVELOPMENT"; chain["bundle"]["plan_id"] = "active_g1_alias"; _resign("RawAuthorityBundleManifestV1", chain["bundle"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_ACTIVE_G1_FORBIDDEN")
        chain = _chain(); chain["admission"]["reason_codes"] = ["NONE"]; _resign("EvidenceAdmissionContextV1", chain["admission"])
        self.assertEqual(_admission_reason(chain), "MSTA_P1A_E_SCHEMA_EXACT")


if __name__ == "__main__":
    unittest.main()
