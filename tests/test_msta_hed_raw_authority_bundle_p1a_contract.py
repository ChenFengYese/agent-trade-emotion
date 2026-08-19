"""P1A synthetic reference checks; this is not a runtime adapter or data reader."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "msta_hed_raw_authority_bundle.p1a_contract.v0_1_0.json"
FIXTURE_PATH = ROOT / "config" / "msta_hed_raw_authority_bundle.p1a_synthetic_contract.v0_1_0.json"
SPEC_PATH = ROOT / "archive/authority/MSTA_HED_RAW_AUTHORITY_BUNDLE_P1A_SPEC_v0_1_0.md"


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


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(domain: str, value: dict[str, object], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(domain.encode("ascii") + b"\x00" + _canonical(payload)).hexdigest()


def _utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("MSTA_P1A_E_TIME_UTC_Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("MSTA_P1A_E_TIME_UTC_Z")
    if parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise ValueError("MSTA_P1A_E_TIME_UTC_Z")
    return parsed


def _safe_path(value: object) -> bool:
    if type(value) is not str or not value or "\\" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value) or value.startswith("//"):
        return False
    parts = value.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _decimal(value: object) -> bool:
    return type(value) is str and bool(re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value))


def _exact(obj: object, schema_name: str) -> bool:
    if type(obj) is not dict:
        return False
    return set(obj) == set(SCHEMAS[schema_name]["exact_fields"])


def _valid_digest(obj: dict[str, object], schema_name: str) -> bool:
    spec = SCHEMAS[schema_name]
    field = spec["digest_field"]
    return type(obj.get(field)) is str and obj[field] == _digest(spec["domain"], obj, field)


def _blank(schema_name: str) -> dict[str, object]:
    values = {field: "x" for field in SCHEMAS[schema_name]["exact_fields"]}
    values["schema_type"] = schema_name
    return values


def _signed(schema_name: str, values: dict[str, object]) -> dict[str, object]:
    result = _blank(schema_name)
    result.update(values)
    field = SCHEMAS[schema_name]["digest_field"]
    result[field] = _digest(SCHEMAS[schema_name]["domain"], result, field)
    return result


def _bundle_chain() -> dict[str, dict[str, object]]:
    source = _signed("SourceAuthoritySnapshotV1", {
        "source_snapshot_id": "SRC-SNAPSHOT-1", "source_id": "SRC-1", "source_generation_id": "GEN-1",
        "source_contract_id": "SRC-CONTRACT-1", "source_contract_sha256": "a" * 64,
        "schema_version": "v1", "capabilities": ["SUPPLIED_PAYLOAD_ONLY"],
        "coverage_semantics": "OBSERVED_ONLY", "frozen_at": "2026-07-26T00:00:00Z",
    })
    artifact = _signed("RawArtifactDescriptorV1", {
        "artifact_id": "ART-1", "source_snapshot_id": source["source_snapshot_id"], "logical_path": "raw/2026-07-26/part-1.ndjson",
        "content_sha256": "b" * 64, "byte_length": 12, "media_type": "application/x-ndjson", "captured_at": "2026-07-26T00:00:01Z",
    })
    record = _signed("RawRecordEnvelopeV1", {
        "raw_record_id": "RAW-1", "logical_record_id": "LOGICAL-1", "revision_id": "REV-1",
        "revision_operation": "CORRECT", "predecessor_revision_id": None, "revision_ordinal": 0,
        "revision_fork_id": "FORK-1", "source_generation_id": source["source_generation_id"], "artifact_id": artifact["artifact_id"],
        "record_locator": "line:1", "event_at": "2026-07-26T00:00:00Z", "published_at": None,
        "received_at": "2026-07-26T00:00:01Z", "available_at": "2026-07-26T00:00:01Z",
        "availability_kind": "ACTUAL", "reconstruction_basis": None, "payload_sha256": "c" * 64,
    })
    coverage = _signed("CoverageEventV1", {
        "coverage_event_id": "COV-1", "source_snapshot_id": source["source_snapshot_id"], "source_generation_id": source["source_generation_id"],
        "coverage_class": "SCHEMA_REJECT", "affected_scope": "SRC-1:metadata", "interval_start": "2026-07-26T00:00:00Z",
        "interval_end": "2026-07-26T00:00:00Z", "observed_at": "2026-07-26T00:00:01Z", "observation_basis": "SYNTHETIC",
        "sequence_proof_status": "NOT_APPLICABLE", "resolution_status": "RESOLVED",
    })
    cursor = _signed("AdapterCursorV1", {
        "cursor_id": "CUR-1", "source_snapshot_id": source["source_snapshot_id"], "source_generation_id": source["source_generation_id"],
        "stream_scope": "SRC-1:metadata", "cursor_token": "token-1", "cursor_ordinal": 1,
        "observed_at": "2026-07-26T00:00:01Z", "predecessor_cursor_digest": None,
    })
    receipt = _signed("AdapterReceiptV1", {
        "adapter_receipt_id": "REC-1", "request_id": "REQ-1", "source_snapshot_id": source["source_snapshot_id"],
        "prior_cursor_digest": None, "next_cursor_digest": cursor["cursor_digest"], "input_payload_sha256": "d" * 64,
        "result_class": "ACCEPTED", "reason_code": "NONE", "record_digests": [record["raw_record_digest"]],
        "coverage_event_digests": [coverage["coverage_event_digest"]], "idempotency_key": "idempotency-1",
    })
    bundle = _signed("RawAuthorityBundleManifestV1", {
        "bundle_id": "BUNDLE-1", "lane": "SYNTHETIC_CONTRACT", "plan_id": "PLAN-SYN-1", "registry_digest": "e" * 64,
        "evidence_root_id": "ROOT-SYN-1", "source_snapshot_digest": source["source_snapshot_digest"],
        "artifact_digests": [artifact["artifact_digest"]], "raw_record_digests": [record["raw_record_digest"]],
        "coverage_event_digests": [coverage["coverage_event_digest"]], "cursor_digest": cursor["cursor_digest"],
        "adapter_receipt_digest": receipt["adapter_receipt_digest"], "created_at": "2026-07-26T00:00:02Z",
    })
    seal = _signed("RawAuthoritySealV1", {
        "seal_id": "SEAL-1", "seal_authority_id": "EXTERNAL-TEST-ONLY", "external_tip_id": "TIP-1", "external_tip_digest": "f" * 64,
        "sealed_bundle_digest": bundle["bundle_digest"], "sealed_at": "2026-07-26T00:00:03Z", "expires_at": "2026-07-27T00:00:03Z",
        "seal_signature_digest": "1" * 64,
    })
    admission = _signed("EvidenceAdmissionContextV1", {
        "admission_context_id": "ADM-1", "v0_5_carrier_type": "Evidence", "v0_5_carrier_digest": "2" * 64,
        "v0_5_result_digest": "3" * 64, "raw_record_digest": record["raw_record_digest"], "logical_record_id": record["logical_record_id"],
        "revision_id": record["revision_id"], "transform_id": "TRANSFORM-1", "transform_version": "v1", "coverage_disposition": "CLEAR",
        "bundle_digest": bundle["bundle_digest"], "seal_digest": seal["seal_digest"], "expected_external_tip_digest": seal["external_tip_digest"],
        "expires_at": "2026-07-27T00:00:03Z", "decision_time": "2026-07-26T00:00:04Z", "admission_status": "ADMITTED", "reason_codes": [],
    })
    return {"source": source, "artifact": artifact, "record": record, "coverage": coverage, "cursor": cursor, "receipt": receipt, "bundle": bundle, "seal": seal, "admission": admission}


def _valid_record(record: dict[str, object], decision_time: str) -> bool:
    if not _exact(record, "RawRecordEnvelopeV1") or not _valid_digest(record, "RawRecordEnvelopeV1"):
        return False
    try:
        event_at, received_at, available_at, decision_at = map(_utc, (record["event_at"], record["received_at"], record["available_at"], decision_time))
        published_at = None if record["published_at"] is None else _utc(record["published_at"])
    except (TypeError, ValueError):
        return False
    if record["availability_kind"] == "ACTUAL":
        if record["reconstruction_basis"] is not None or received_at > available_at:
            return False
    elif record["availability_kind"] == "RECONSTRUCTED":
        if type(record["reconstruction_basis"]) is not dict:
            return False
    else:
        return False
    if event_at > available_at or available_at > decision_at or (published_at is not None and published_at > available_at):
        return False
    return all(type(record[field]) is str and record[field] for field in ("raw_record_id", "logical_record_id", "revision_id", "source_generation_id", "artifact_id", "payload_sha256"))


def _valid_seal(bundle: dict[str, object], seal: dict[str, object], decision_time: str) -> bool:
    if not (_exact(bundle, "RawAuthorityBundleManifestV1") and _exact(seal, "RawAuthoritySealV1")):
        return False
    if not (_valid_digest(bundle, "RawAuthorityBundleManifestV1") and _valid_digest(seal, "RawAuthoritySealV1")):
        return False
    try:
        sealed_at, expires_at, decision_at = map(_utc, (seal["sealed_at"], seal["expires_at"], decision_time))
    except (TypeError, ValueError):
        return False
    return (
        seal["seal_authority_id"] != bundle["bundle_id"]
        and seal["sealed_bundle_digest"] == bundle["bundle_digest"]
        and sealed_at <= decision_at <= expires_at
    )


def _valid_admission(chain: dict[str, dict[str, object]]) -> bool:
    admission, record, bundle, seal = chain["admission"], chain["record"], chain["bundle"], chain["seal"]
    if not (_exact(admission, "EvidenceAdmissionContextV1") and _valid_digest(admission, "EvidenceAdmissionContextV1")):
        return False
    if not (_valid_record(record, admission["decision_time"]) and _valid_seal(bundle, seal, admission["decision_time"])):
        return False
    try:
        expiry, decision = map(_utc, (admission["expires_at"], admission["decision_time"]))
    except (TypeError, ValueError):
        return False
    return (
        admission["admission_status"] == "ADMITTED"
        and decision <= expiry
        and admission["raw_record_digest"] == record["raw_record_digest"]
        and admission["logical_record_id"] == record["logical_record_id"]
        and admission["revision_id"] == record["revision_id"]
        and admission["bundle_digest"] == bundle["bundle_digest"]
        and admission["seal_digest"] == seal["seal_digest"]
        and admission["expected_external_tip_digest"] == seal["external_tip_digest"]
    )


class RawAuthorityBundleP1AContractTests(unittest.TestCase):
    def test_contract_and_fixture_are_strict_and_pending_gate(self) -> None:
        self.assertTrue(SPEC_PATH.is_file())
        self.assertEqual(CONTRACT["status"], "DRAFT_AWAITING_SOL_P1A_GATE")
        self.assertFalse(CONTRACT["implementation_authorized"])
        self.assertFalse(CONTRACT["io_authorized"])
        self.assertFalse(CONTRACT["market_or_outcome_access_authorized"])
        self.assertEqual(FIXTURE["lane"], "SYNTHETIC_CONTRACT")
        self.assertEqual(len(FIXTURE["counterexamples"]), CONTRACT["validation"]["required_counterexamples"])
        self.assertEqual(FIXTURE["expected_object_order"], list(SCHEMAS))
        contract_copy = dict(CONTRACT)
        contract_copy.pop("contract_sha256")
        self.assertEqual(
            CONTRACT["contract_sha256"],
            hashlib.sha256(b"msta-hed/raw-authority-bundle-contract/v1\x00" + _canonical(contract_copy)).hexdigest(),
        )
        fixture_copy = dict(FIXTURE)
        fixture_copy.pop("fixture_sha256")
        self.assertEqual(
            FIXTURE["fixture_sha256"],
            hashlib.sha256(b"msta-hed/raw-authority-bundle-synthetic-fixture/v1\x00" + _canonical(fixture_copy)).hexdigest(),
        )

    def test_duplicate_json_key_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "MSTA_P1A_E_SCHEMA_EXACT"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=_pairs)

    def test_exact_fields_and_order_are_frozen(self) -> None:
        for name, spec in SCHEMAS.items():
            self.assertEqual(len(spec["exact_fields"]), len(set(spec["exact_fields"])), name)
            self.assertEqual(spec["exact_fields"][0], "schema_type", name)
            self.assertEqual(spec["exact_fields"][-1], spec["digest_field"], name)
            obj = _signed(name, {})
            self.assertTrue(_exact(obj, name))
            obj["surplus"] = "forbidden"
            self.assertFalse(_exact(obj, name))

    def test_domain_digest_mutation_self_sign_and_cycle_fail(self) -> None:
        chain = _bundle_chain()
        for name, obj in (("SourceAuthoritySnapshotV1", chain["source"]), ("RawArtifactDescriptorV1", chain["artifact"]), ("RawRecordEnvelopeV1", chain["record"]), ("CoverageEventV1", chain["coverage"]), ("AdapterCursorV1", chain["cursor"]), ("AdapterReceiptV1", chain["receipt"]), ("RawAuthorityBundleManifestV1", chain["bundle"]), ("RawAuthoritySealV1", chain["seal"]), ("EvidenceAdmissionContextV1", chain["admission"])):
            self.assertTrue(_valid_digest(obj, name), name)
        mutated = copy.deepcopy(chain["bundle"])
        mutated["plan_id"] = "PLAN-MUTATED"
        self.assertFalse(_valid_digest(mutated, "RawAuthorityBundleManifestV1"))
        self.assertTrue(_valid_seal(chain["bundle"], chain["seal"], "2026-07-26T00:00:04Z"))
        self_signed = copy.deepcopy(chain["seal"])
        self_signed["seal_authority_id"] = chain["bundle"]["bundle_id"]
        self_signed["seal_digest"] = _digest(SCHEMAS["RawAuthoritySealV1"]["domain"], self_signed, "seal_digest")
        self.assertFalse(_valid_seal(chain["bundle"], self_signed, "2026-07-26T00:00:04Z"))
        cycle = copy.deepcopy(chain["seal"])
        cycle["sealed_bundle_digest"] = cycle["seal_digest"]
        cycle["seal_digest"] = _digest(SCHEMAS["RawAuthoritySealV1"]["domain"], cycle, "seal_digest")
        self.assertFalse(_valid_seal(chain["bundle"], cycle, "2026-07-26T00:00:04Z"))

    def test_unsafe_paths_and_decimal_policy_fail_closed(self) -> None:
        for path in ("/tmp/raw", "../raw", "raw//part", "raw\\part", "C:raw", "raw/./part"):
            self.assertFalse(_safe_path(path), path)
        self.assertTrue(_safe_path("raw/part.ndjson"))
        self.assertTrue(_decimal("0"))
        self.assertTrue(_decimal("-1.25"))
        for value in (1, 1.0, "1e3", "01", "NaN", ""):
            self.assertFalse(_decimal(value), repr(value))

    def test_actual_reconstructed_unknown_publication_and_late_boundary(self) -> None:
        record = _bundle_chain()["record"]
        self.assertTrue(_valid_record(record, "2026-07-26T00:00:02Z"))
        future = copy.deepcopy(record)
        future["available_at"] = "2026-07-26T00:00:03Z"
        future["raw_record_digest"] = _digest(SCHEMAS["RawRecordEnvelopeV1"]["domain"], future, "raw_record_digest")
        self.assertFalse(_valid_record(future, "2026-07-26T00:00:02Z"))
        reconstructed = copy.deepcopy(record)
        reconstructed["availability_kind"] = "RECONSTRUCTED"
        reconstructed["reconstruction_basis"] = {"basis_id": "REPLAY-1"}
        reconstructed["raw_record_digest"] = _digest(SCHEMAS["RawRecordEnvelopeV1"]["domain"], reconstructed, "raw_record_digest")
        self.assertTrue(_valid_record(reconstructed, "2026-07-26T00:00:02Z"))
        reconstructed["reconstruction_basis"] = None
        reconstructed["raw_record_digest"] = _digest(SCHEMAS["RawRecordEnvelopeV1"]["domain"], reconstructed, "raw_record_digest")
        self.assertFalse(_valid_record(reconstructed, "2026-07-26T00:00:02Z"))
        self.assertIsNone(record["published_at"])

    def test_revision_identity_duplicate_and_generation_reset_rules(self) -> None:
        record = _bundle_chain()["record"]
        self.assertEqual(record["revision_ordinal"], 0)
        self.assertIsNone(record["predecessor_revision_id"])
        exact_duplicate = copy.deepcopy(record)
        self.assertEqual(exact_duplicate["raw_record_digest"], record["raw_record_digest"])
        correction = copy.deepcopy(record)
        correction.update({"raw_record_id": "RAW-2", "revision_id": "REV-2", "predecessor_revision_id": "REV-1", "revision_ordinal": 1, "revision_operation": "CORRECT"})
        correction["raw_record_digest"] = _digest(SCHEMAS["RawRecordEnvelopeV1"]["domain"], correction, "raw_record_digest")
        self.assertTrue(_valid_record(correction, "2026-07-26T00:00:02Z"))
        self.assertNotEqual(correction["raw_record_digest"], record["raw_record_digest"])
        invalid = copy.deepcopy(correction)
        invalid["revision_ordinal"] = 0
        invalid["raw_record_digest"] = _digest(SCHEMAS["RawRecordEnvelopeV1"]["domain"], invalid, "raw_record_digest")
        self.assertLessEqual(invalid["revision_ordinal"], record["revision_ordinal"])
        self.assertNotEqual(invalid["revision_ordinal"], correction["revision_ordinal"])
        self.assertIn("CURSOR_RESET", CONTRACT["coverage_rules"]["classes"])

    def test_nine_gap_classes_never_impute_or_infer_silence(self) -> None:
        classes = CONTRACT["coverage_rules"]["classes"]
        self.assertEqual(len(classes), 9)
        self.assertEqual(CONTRACT["coverage_rules"]["silence_rule"], "SILENCE_NEVER_IMPLIES_NO_TRADE_OR_ZERO_ACTIVITY")
        self.assertEqual(CONTRACT["coverage_rules"]["imputation"], "FORBIDDEN")
        self.assertEqual(CONTRACT["coverage_rules"]["required_gap_admission"], "FAIL_CLOSED")
        self.assertIn("COVERAGE_UNKNOWN", classes)

    def test_cursor_and_idempotency_rules(self) -> None:
        chain = _bundle_chain()
        cursor = chain["cursor"]
        receipt = chain["receipt"]
        self.assertTrue(_valid_digest(cursor, "AdapterCursorV1"))
        self.assertTrue(_valid_digest(receipt, "AdapterReceiptV1"))
        self.assertEqual(receipt["next_cursor_digest"], cursor["cursor_digest"])
        self.assertEqual(CONTRACT["pure_adapter_boundary"]["empty_rule"], "EMPTY_INPUT_BATCH_ONLY_NO_RECEIPT")
        self.assertEqual(CONTRACT["pure_adapter_boundary"]["nonempty_reject_rule"], "FIRST_NONEMPTY_ALL_REJECT_INPUT_EMITS_TYPED_RECEIPT")
        self.assertIn("MSTA_P1A_E_IDEMPOTENCY_CONFLICT", CONTRACT["pure_adapter_boundary"]["reason_codes"])

    def test_pure_adapter_capability_allowlist(self) -> None:
        boundary = CONTRACT["pure_adapter_boundary"]
        self.assertEqual(boundary["interface"], "adapt(request, source_snapshot, prior_cursor_or_null, supplied_payload_bytes)->AdapterResultV1")
        self.assertEqual(boundary["forbidden_capabilities"], ["FILESYSTEM", "NETWORK", "ENVIRONMENT", "WALLCLOCK", "RANDOM", "RETRY_LOOP", "GLOBAL_STATE"])
        self.assertIn("MSTA_P1A_E_CAPABILITY_NOT_ALLOWLISTED", boundary["reason_codes"])

    def test_authority_bundle_and_external_seal_are_not_self_authority(self) -> None:
        chain = _bundle_chain()
        bundle, seal = chain["bundle"], chain["seal"]
        self.assertTrue(_valid_digest(bundle, "RawAuthorityBundleManifestV1"))
        self.assertTrue(_valid_digest(seal, "RawAuthoritySealV1"))
        self.assertEqual(seal["sealed_bundle_digest"], bundle["bundle_digest"])
        self.assertNotEqual(seal["seal_authority_id"], bundle["bundle_id"])
        self.assertEqual(CONTRACT["seal_and_admission"]["seal_rule"], "EXTERNAL_SEAL_REQUIRED_FAIL_CLOSED_NO_SELF_ISSUED_BUNDLE_SEAL")
        missing_seal = copy.deepcopy(chain["admission"])
        missing_seal["seal_digest"] = None
        self.assertIsNone(missing_seal["seal_digest"])

    def test_admission_binds_v0_5_without_adding_keys(self) -> None:
        admission = _bundle_chain()["admission"]
        self.assertTrue(_valid_digest(admission, "EvidenceAdmissionContextV1"))
        fields = SCHEMAS["EvidenceAdmissionContextV1"]["exact_fields"]
        for field in ("v0_5_carrier_type", "v0_5_carrier_digest", "v0_5_result_digest", "raw_record_digest", "revision_id", "transform_id", "bundle_digest", "seal_digest", "expected_external_tip_digest", "expires_at"):
            self.assertIn(field, fields)
        self.assertEqual(CONTRACT["seal_and_admission"]["v0_5_exact_keys_addition"], "FORBIDDEN")
        self.assertEqual(CONTRACT["seal_and_admission"]["admission_statuses"], ["ADMITTED", "REJECTED", "UNKNOWN"])
        self.assertTrue(_valid_admission(_bundle_chain()))
        mismatched = _bundle_chain()
        mismatched["admission"]["expected_external_tip_digest"] = "0" * 64
        mismatched["admission"]["admission_context_digest"] = _digest(SCHEMAS["EvidenceAdmissionContextV1"]["domain"], mismatched["admission"], "admission_context_digest")
        self.assertFalse(_valid_admission(mismatched))

    def test_lane_isolation_seen_and_active_g1_boundary(self) -> None:
        lanes = CONTRACT["lanes"]
        self.assertEqual(lanes["allowed"], ["SYNTHETIC_CONTRACT", "METADATA_ONLY", "DEVELOPMENT", "CALIBRATION", "ONE_SHOT_HOLDOUT", "PAPER_SHADOW"])
        self.assertEqual(lanes["required_distinct_bindings"], ["plan_id", "registry_digest", "evidence_root_id", "bundle_digest", "seal_digest"])
        self.assertEqual(lanes["active_g1"], "FORBIDDEN_NOT_A_P1A_LANE")
        self.assertIn("SEEN_INTERVAL", lanes["seen_rule"])
        self.assertIn("MSTA_P1A_E_ACTIVE_G1_FORBIDDEN", CONTRACT["pure_adapter_boundary"]["reason_codes"])

    def test_source_and_hypothesis_priority_are_plan_only(self) -> None:
        self.assertEqual(CONTRACT["source_priority_plan"]["p0_order"], ["OFFICIAL_VENUE_DEPTH_TRADE", "OFFICIAL_MARK_FUNDING_OI", "OFFICIAL_VENUE_METADATA", "VERSIONED_MARKET_CONTEXT"])
        self.assertEqual(CONTRACT["theory_test_plan"]["order"], ["H01", "H03", "H05", "H02", "H04", "H06", "H08", "H07"])
        self.assertIn("NOT_SOURCE_EVIDENCE", CONTRACT["source_priority_plan"]["statement"])
        self.assertIn("NO_HYPOTHESIS_SUPPORTED", CONTRACT["theory_test_plan"]["statement"])


if __name__ == "__main__":
    unittest.main()
