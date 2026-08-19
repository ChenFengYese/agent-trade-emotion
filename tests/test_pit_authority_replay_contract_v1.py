from __future__ import annotations

import ast
import copy
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from trade_system.pit_authority_replay_contract_v1 import (
    CONTRACT_DOCUMENTS,
    ROUTE_AUTHORITY,
    SOURCE_DISCOVERY_DOCUMENT,
    synthetic_external_authority,
    synthetic_raw_bytes,
    validate_adapter_fixture,
    validate_admission_fixture,
    validate_barrier_fixture,
    validate_chronology_fixture,
    validate_comparison_fixture,
    validate_d0_candidate,
    validate_pitar1_contract_bundle,
    validate_replay_receipt_fixture,
    validate_revision_fixture,
    validate_source_discovery_document,
    validate_trajectory_fixture,
)


ROOT = Path(__file__).resolve().parents[1]


def independent_digest(domain: str, document: dict[str, Any], field: str) -> str:
    unsigned = copy.deepcopy(document)
    unsigned.pop(field, None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("utf-8") + b"\x00" + canonical).hexdigest()


def load_contract_bytes() -> dict[str, bytes]:
    return {path: (ROOT / path).read_bytes() for path in CONTRACT_DOCUMENTS}


def make_clean_candidate(profile: str = "nonempty") -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    raw = synthetic_raw_bytes(profile)
    authority = synthetic_external_authority(profile)
    raw_sha = hashlib.sha256(raw).hexdigest()
    suffix = profile
    bundle = {
        "bundle_id": f"pitar1.synthetic-bundle.{suffix}.v1",
        "route_id": ROUTE_AUTHORITY["route_id"],
        "plan_id": authority["plan_id"],
        "lane": authority["lane"],
        "source_authority": copy.deepcopy(authority["source_authority"]),
        "artifact_authority": copy.deepcopy(authority["artifact_authority"]),
        "transform_authority": copy.deepcopy(authority["transform_authority"]),
        "proof_authority": copy.deepcopy(authority["proof_authority"]),
        "tip_authority": copy.deepcopy(authority["tip_authority"]),
        "coverage_state": authority["coverage_state"],
        "revision_chain_sha256": authority["revision_chain_sha256"],
        "created_at": "2024-06-02T00:00:03Z",
        "bundle_sha256": "",
    }
    bundle["bundle_sha256"] = independent_digest(
        "pitar1/synthetic-authority-bundle/v1", bundle, "bundle_sha256"
    )
    row = {
        "source_id": authority["source_authority"]["authority_id"],
        "authority_grade": "A",
        "instrument_id": f"pitar1.synthetic-instrument.{suffix}.v1",
        "source_event_id": f"pitar1.synthetic-source-event.{suffix}.v1",
        "event_id": f"pitar1.synthetic-event.{suffix}.v1",
        "logical_id": f"pitar1.synthetic-logical.{suffix}.v1",
        "revision_id": f"pitar1.synthetic-revision.{suffix}.initial",
        "supersedes_revision_id": None,
        "operation": "INITIAL",
        "revision_ordinal": 0,
        "revision_fork_id": f"pitar1.synthetic-fork.{suffix}.main",
        "event_time": "2024-06-01T23:59:00Z",
        "published_at": "2024-06-02T00:00:00Z",
        "received_at": "2024-06-02T00:00:01Z",
        "ingested_at": "2024-06-02T00:00:02Z",
        "admission_validated_at": "2024-06-02T00:00:03Z",
        "available_at": "2024-06-02T00:00:03Z",
        "raw_artifact_sha256": raw_sha,
        "raw_byte_offset_or_member_id": authority["artifact_authority"]["member_id"],
        "payload_sha256": raw_sha,
        "parser_version": authority["transform_authority"]["parser_id"],
        "source_sequence": 1,
        "source_sequence_kind": "NATIVE",
        "coverage_state": authority["coverage_state"],
    }
    proof = {
        "proof_id": authority["proof_authority"]["proof_id"],
        "proof_sha256": authority["proof_authority"]["proof_sha256"],
        "coverage_state": authority["coverage_state"],
        "source_event_id": row["source_event_id"],
        "logical_id": row["logical_id"],
        "decision_at": "2024-06-03T00:00:00Z",
        "evidence_available_at": "2024-06-02T00:00:03Z",
    }
    source_authority_sha = independent_digest(
        "pitar1/source-authority/v1", bundle["source_authority"], "__no_digest_field__"
    )
    receipt = {
        "receipt_id": f"pitar1.synthetic-receipt.{suffix}.v1",
        "admission_id": f"pitar1.synthetic-admission.{suffix}.v1",
        "bundle_sha256": bundle["bundle_sha256"],
        "raw_artifact_sha256": raw_sha,
        "raw_byte_length": len(raw),
        "payload_sha256": raw_sha,
        "source_authority_sha256": source_authority_sha,
        "schema_sha256": authority["transform_authority"]["schema_sha256"],
        "transform_sha256": authority["transform_authority"]["transform_sha256"],
        "parser_sha256": authority["transform_authority"]["parser_sha256"],
        "proof_sha256": authority["proof_authority"]["proof_sha256"],
        "tip_sha256": authority["tip_authority"]["tip_sha256"],
        "coverage_state": authority["coverage_state"],
        "revision_chain_sha256": authority["revision_chain_sha256"],
        "admission_validated_at": row["admission_validated_at"],
        "decision_at": proof["decision_at"],
        "permission": "DENIED",
        "action": "ABSTAIN",
        "max_risk": 0,
        "receipt_sha256": "",
    }
    receipt["receipt_sha256"] = independent_digest(
        "pitar1/synthetic-admission-receipt/v1", receipt, "receipt_sha256"
    )
    return raw, authority, {
        "authority_bundle": bundle,
        "raw_record": row,
        "coverage_proof": proof,
        "admission_receipt": receipt,
    }


def make_revision_row(
    *,
    event_id: str,
    revision_id: str,
    ordinal: int,
    supersedes: str | None,
    operation: str,
    available_at: str,
    source_sequence: int,
    payload_sha256: str | None = None,
    coverage_state: str = "CONTINUOUS_OBSERVED",
) -> dict[str, Any]:
    payload = payload_sha256 or hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    return {
        "source_id": "pitar1.synthetic-revision-source.v1",
        "authority_grade": "A",
        "instrument_id": "pitar1.synthetic-instrument.revision.v1",
        "source_event_id": f"{event_id}.source",
        "event_id": event_id,
        "logical_id": "pitar1.synthetic-logical.revision.v1",
        "revision_id": revision_id,
        "supersedes_revision_id": supersedes,
        "operation": operation,
        "revision_ordinal": ordinal,
        "revision_fork_id": "pitar1.synthetic-fork.revision.main",
        "event_time": "2024-05-31T23:59:00Z",
        "published_at": "2024-06-01T00:00:00Z",
        "received_at": available_at,
        "ingested_at": available_at,
        "admission_validated_at": available_at,
        "available_at": available_at,
        "raw_artifact_sha256": hashlib.sha256(b"revision fixture").hexdigest(),
        "raw_byte_offset_or_member_id": source_sequence,
        "payload_sha256": payload,
        "parser_version": "pitar1.synthetic-parser.revision.v1",
        "source_sequence": source_sequence,
        "source_sequence_kind": "NATIVE",
        "coverage_state": coverage_state,
    }


def make_adapter_fixture() -> dict[str, Any]:
    return {
        "fixture_id": "pitar1.synthetic-adapter-interface.v1",
        "fixture_kind": "SYNTHETIC_INTERFACE_ASSERTION",
        "request_fields": [
            "request_id",
            "plan_id",
            "artifact_id",
            "admission_receipt_sha256",
            "schema_sha256",
            "transform_sha256",
            "parser_sha256",
            "prior_cursor_sha256",
            "decision_at",
        ],
        "result_fields": [
            "result_id",
            "request_id",
            "record_digests",
            "coverage_event_digests",
            "quarantine_event_digests",
            "next_cursor_sha256",
            "adapter_receipt_sha256",
            "result_class",
        ],
        "sort_key": ["available_at", "source_sequence", "event_id"],
        "observed_operations": [],
        "runtime_executed": False,
        "permission": "DENIED",
        "action": "ABSTAIN",
        "max_risk": 0,
    }


def make_comparison_fixture() -> dict[str, Any]:
    policies = [
        "DYNAMIC_MULTI_PATH",
        "FROZEN_ENTRY_STATIC_EXIT",
        "SINGLE_PATH",
        "NO_TRADE",
    ]
    information = hashlib.sha256(b"same admitted events").hexdigest()
    denominator = hashlib.sha256(b"same opportunity denominator").hexdigest()
    costs = hashlib.sha256(b"same cost model").hexdigest()
    risk = hashlib.sha256(b"same risk model").hexdigest()
    return {
        "policy_ids": policies,
        "information_digest_by_policy": {policy: information for policy in policies},
        "denominator_digest_by_policy": {policy: denominator for policy in policies},
        "cost_model_digest_by_policy": {policy: costs for policy in policies},
        "risk_model_digest_by_policy": {policy: risk for policy in policies},
        "policy_input_fields": ["available_at", "coverage_state", "admitted_payload"],
        "outcome_only_fields": ["mfe_post_outcome_only", "mae_post_outcome_only"],
        "real_data": False,
        "scoring_executed": False,
        "permission": "DENIED",
        "action": "ABSTAIN",
        "max_risk": 0,
    }


def make_replay_receipt(
    *,
    receipt_id: str,
    prior_digest: str | None,
    first_event_id: str,
    last_event_id: str,
    first_sequence: int,
    last_sequence: int,
) -> dict[str, Any]:
    receipt = {
        "replay_receipt_id": receipt_id,
        "prior_replay_receipt_sha256": prior_digest,
        "admitted_artifact_set_sha256": hashlib.sha256(b"admitted artifacts").hexdigest(),
        "adapter_version_sha256": hashlib.sha256(b"adapter version").hexdigest(),
        "configuration_sha256": hashlib.sha256(b"configuration").hexdigest(),
        "first_event_key": [
            "2024-06-01T00:00:03Z",
            first_sequence,
            first_event_id,
        ],
        "last_event_key": [
            "2024-06-02T00:00:03Z",
            last_sequence,
            last_event_id,
        ],
        "event_count": last_sequence - first_sequence + 1,
        "state_transition_sha256": hashlib.sha256(
            f"{receipt_id}/state".encode("utf-8")
        ).hexdigest(),
        "created_at": "2024-06-03T00:00:00Z",
        "replay_receipt_sha256": "",
    }
    receipt["replay_receipt_sha256"] = independent_digest(
        "pitar1/synthetic-replay-receipt/v1",
        receipt,
        "replay_receipt_sha256",
    )
    return receipt


def make_trajectory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for policy in (
        "DYNAMIC_MULTI_PATH",
        "FROZEN_ENTRY_STATIC_EXIT",
        "SINGLE_PATH",
        "NO_TRADE",
    ):
        rows.append(
            {
                "opportunity_id": "pitar1.synthetic-opportunity.v1",
                "policy_id": policy,
                "graph_revision_count": 0,
                "path_revision_count": 0,
                "leader_switch_count": 0,
                "graph_update_latency": 0.0,
                "decision_latency": 0.0,
                "entry_count": 0,
                "cancel_count": 0,
                "replace_count": 0,
                "fill_count": 0,
                "partial_fill_count": 0,
                "stop_revision_count": 0,
                "target_revision_count": 0,
                "horizon_revision_count": 0,
                "fees": 0.0,
                "slippage": 0.0,
                "funding": 0.0,
                "tail_loss": 0.0,
                "risk_breach_count": 0,
                "coverage_state": "CONTINUOUS_OBSERVED",
                "abstain_state": policy == "NO_TRADE",
                "unknown_state": False,
                "censor_state": False,
                "mfe_post_outcome_only": None,
                "mae_post_outcome_only": None,
            }
        )
    return rows


class ContractBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = load_contract_bytes()

    def test_exact_contract_bundle_is_local_review_ready_only(self) -> None:
        result = validate_pitar1_contract_bundle(self.documents, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["status"], "VALID_E0_CANDIDATE")
        self.assertEqual(result["permission"], "DENIED")
        self.assertEqual(result["action"], "ABSTAIN")
        self.assertEqual(result["max_risk"], 0)
        self.assertTrue(result["details"]["external_stage_gate_required"])

    def test_order_independent(self) -> None:
        items = list(reversed(list(self.documents.items())))
        result = validate_pitar1_contract_bundle(items, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["status"], "VALID_E0_CANDIDATE")

    def test_duplicate_document_path_rejected(self) -> None:
        items = list(self.documents.items())
        items.append(items[0])
        result = validate_pitar1_contract_bundle(items, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["reason_code"], "DUPLICATE_DOCUMENT_PATH")

    def test_missing_and_unknown_documents_rejected(self) -> None:
        missing = dict(self.documents)
        missing.pop(next(iter(missing)))
        self.assertEqual(
            validate_pitar1_contract_bundle(missing, copy.deepcopy(ROUTE_AUTHORITY))["reason_code"],
            "DOCUMENT_SET_MISMATCH",
        )
        extra = dict(self.documents)
        extra["config/pitar1.unknown.v1.json"] = b"{}"
        self.assertEqual(
            validate_pitar1_contract_bundle(extra, copy.deepcopy(ROUTE_AUTHORITY))["reason_code"],
            "DOCUMENT_SET_MISMATCH",
        )

    def test_external_route_cannot_be_candidate_defined(self) -> None:
        mutated = copy.deepcopy(ROUTE_AUTHORITY)
        mutated["head"] = "0" * 40
        result = validate_pitar1_contract_bundle(self.documents, mutated)
        self.assertEqual(result["reason_code"], "EXTERNAL_ROUTE_AUTHORITY_MISMATCH")

    def test_duplicate_json_keys_rejected(self) -> None:
        mutated = dict(self.documents)
        path = next(iter(mutated))
        mutated[path] = b'{"schema_version":"a","schema_version":"b"}'
        result = validate_pitar1_contract_bundle(mutated, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["reason_code"], "DUPLICATE_JSON_KEY")

    def test_nonfinite_json_rejected(self) -> None:
        mutated = dict(self.documents)
        path = next(iter(mutated))
        mutated[path] = b'{"x":NaN}'
        result = validate_pitar1_contract_bundle(mutated, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["reason_code"], "NONFINITE_NUMBER")

    def test_unknown_top_level_key_rejected_even_when_resigned(self) -> None:
        mutated = dict(self.documents)
        path = next(iter(mutated))
        profile = CONTRACT_DOCUMENTS[path]
        document = json.loads(mutated[path])
        document["candidate_acceptance"] = True
        document["contract_sha256"] = independent_digest(
            profile["domain"], document, "contract_sha256"
        )
        mutated[path] = json.dumps(document).encode("utf-8")
        result = validate_pitar1_contract_bundle(mutated, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["reason_code"], "TOP_LEVEL_SCHEMA_MISMATCH")

    def test_every_contract_leaf_is_bound_to_external_validator_pin(self) -> None:
        checked = 0

        def leaves(value: Any, pointer: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
            if isinstance(value, dict):
                result: list[tuple[Any, ...]] = []
                for key, item in value.items():
                    result.extend(leaves(item, pointer + (key,)))
                return result
            if isinstance(value, list):
                result = []
                for index, item in enumerate(value):
                    result.extend(leaves(item, pointer + (index,)))
                return result
            return [pointer]

        def mutate_leaf(value: Any) -> Any:
            if value is None:
                return "mutated"
            if isinstance(value, bool):
                return not value
            if isinstance(value, int):
                return value + 1
            if isinstance(value, float):
                return value + 0.125
            if isinstance(value, str):
                return value + "x"
            raise AssertionError(type(value))

        for path, raw in self.documents.items():
            profile = CONTRACT_DOCUMENTS[path]
            original = json.loads(raw)
            for pointer in leaves(original):
                with self.subTest(path=path, pointer=pointer):
                    candidate = copy.deepcopy(original)
                    target: Any = candidate
                    for part in pointer[:-1]:
                        target = target[part]
                    target[pointer[-1]] = mutate_leaf(target[pointer[-1]])
                    if pointer[-1] != "contract_sha256":
                        candidate["contract_sha256"] = independent_digest(
                            profile["domain"], candidate, "contract_sha256"
                        )
                    mutated = dict(self.documents)
                    mutated[path] = json.dumps(candidate).encode("utf-8")
                    result = validate_pitar1_contract_bundle(
                        mutated, copy.deepcopy(ROUTE_AUTHORITY)
                    )
                    self.assertEqual(result["status"], "REJECT")
                    checked += 1
        self.assertGreater(checked, 250)


class SourceDiscoveryTests(unittest.TestCase):
    def test_discovery_record_is_wait_data(self) -> None:
        raw = (ROOT / SOURCE_DISCOVERY_DOCUMENT["path"]).read_bytes()
        result = validate_source_discovery_document(raw, copy.deepcopy(ROUTE_AUTHORITY))
        self.assertEqual(result["status"], "WAIT_DATA")
        self.assertEqual(result["details"]["ready_count"], 0)
        self.assertFalse(result["details"]["market_or_macro_rows_accessed"])

    def test_discovery_ready_escalation_rejected_even_when_resigned(self) -> None:
        raw = json.loads((ROOT / SOURCE_DISCOVERY_DOCUMENT["path"]).read_text())
        raw["status"] = "READY"
        raw["record_sha256"] = independent_digest(
            SOURCE_DISCOVERY_DOCUMENT["domain"], raw, "record_sha256"
        )
        result = validate_source_discovery_document(
            json.dumps(raw), copy.deepcopy(ROUTE_AUTHORITY)
        )
        self.assertEqual(result["reason_code"], "DISCOVERY_DISPOSITION_MISMATCH")

    def test_every_discovery_leaf_is_bound(self) -> None:
        original = json.loads((ROOT / SOURCE_DISCOVERY_DOCUMENT["path"]).read_text())
        leaf_paths: list[tuple[Any, ...]] = []

        def visit(value: Any, pointer: tuple[Any, ...] = ()) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    visit(item, pointer + (key,))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, pointer + (index,))
            else:
                leaf_paths.append(pointer)

        visit(original)
        for pointer in leaf_paths:
            with self.subTest(pointer=pointer):
                candidate = copy.deepcopy(original)
                target: Any = candidate
                for part in pointer[:-1]:
                    target = target[part]
                value = target[pointer[-1]]
                if value is None:
                    changed: Any = "mutated"
                elif isinstance(value, bool):
                    changed = not value
                elif isinstance(value, (int, float)):
                    changed = value + 1
                else:
                    changed = value + "x"
                target[pointer[-1]] = changed
                if pointer[-1] != "record_sha256":
                    candidate["record_sha256"] = independent_digest(
                        SOURCE_DISCOVERY_DOCUMENT["domain"], candidate, "record_sha256"
                    )
                result = validate_source_discovery_document(
                    json.dumps(candidate), copy.deepcopy(ROUTE_AUTHORITY)
                )
                self.assertEqual(result["status"], "REJECT")
        self.assertGreater(len(leaf_paths), 100)


class AdmissionAttackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = load_contract_bytes()
        cls.raw, cls.authority, cls.clean = make_clean_candidate()

    def validate(
        self,
        candidate: dict[str, Any],
        *,
        raw: bytes | None = None,
        authority: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return validate_admission_fixture(
            self.documents,
            copy.deepcopy(ROUTE_AUTHORITY),
            self.raw if raw is None else raw,
            self.authority if authority is None else authority,
            candidate,
        )

    def test_clean_nonempty_admission(self) -> None:
        result = self.validate(copy.deepcopy(self.clean))
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertEqual(result["permission"], "DENIED")

    def test_clean_zero_byte_admission(self) -> None:
        raw, authority, candidate = make_clean_candidate("zero")
        result = validate_admission_fixture(
            self.documents,
            copy.deepcopy(ROUTE_AUTHORITY),
            raw,
            authority,
            candidate,
        )
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertEqual(
            result["details"]["raw_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_arbitrary_transform_authority_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        authority = copy.deepcopy(self.authority)
        changed = "f" * 64
        authority["transform_authority"]["transform_sha256"] = changed
        candidate["authority_bundle"]["transform_authority"]["transform_sha256"] = changed
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"]["bundle_sha256"]
        candidate["admission_receipt"]["transform_sha256"] = changed
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(
            self.validate(candidate, authority=authority)["reason_code"],
            "EXTERNAL_AUTHORITY_NOT_PINNED",
        )

    def test_arbitrary_proof_authority_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        authority = copy.deepcopy(self.authority)
        changed = "e" * 64
        authority["proof_authority"]["proof_sha256"] = changed
        candidate["authority_bundle"]["proof_authority"]["proof_sha256"] = changed
        candidate["coverage_proof"]["proof_sha256"] = changed
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"]["bundle_sha256"]
        candidate["admission_receipt"]["proof_sha256"] = changed
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(
            self.validate(candidate, authority=authority)["reason_code"],
            "EXTERNAL_AUTHORITY_NOT_PINNED",
        )

    def test_arbitrary_tip_authority_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        authority = copy.deepcopy(self.authority)
        changed = "d" * 64
        authority["tip_authority"]["tip_sha256"] = changed
        candidate["authority_bundle"]["tip_authority"]["tip_sha256"] = changed
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"]["bundle_sha256"]
        candidate["admission_receipt"]["tip_sha256"] = changed
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(
            self.validate(candidate, authority=authority)["reason_code"],
            "EXTERNAL_AUTHORITY_NOT_PINNED",
        )

    def test_future_tip_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        authority = copy.deepcopy(self.authority)
        authority["tip_authority"]["committed_at"] = "2024-06-04T00:00:00Z"
        candidate["authority_bundle"]["tip_authority"]["committed_at"] = "2024-06-04T00:00:00Z"
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"]["bundle_sha256"]
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(
            self.validate(candidate, authority=authority)["reason_code"],
            "EXTERNAL_AUTHORITY_NOT_PINNED",
        )

    def test_future_evidence_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["coverage_proof"]["evidence_available_at"] = "2024-06-04T00:00:00Z"
        self.assertEqual(self.validate(candidate)["reason_code"], "FUTURE_EVIDENCE")

    def test_future_bundle_creation_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["authority_bundle"]["created_at"] = "2024-06-04T00:00:00Z"
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"][
            "bundle_sha256"
        ]
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "FUTURE_BUNDLE")

    def test_non_string_payload_hash_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["raw_record"]["payload_sha256"] = 7
        self.assertEqual(self.validate(candidate)["reason_code"], "ROW_PAYLOAD_HASH_INVALID")

    def test_payload_and_input_bytes_mismatch_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        result = self.validate(candidate, raw=b"different explicit bytes")
        self.assertEqual(result["reason_code"], "RAW_EXTERNAL_IDENTITY_MISMATCH")

    def test_wrong_zero_byte_hash_rejected(self) -> None:
        raw, authority, candidate = make_clean_candidate("zero")
        candidate["raw_record"]["raw_artifact_sha256"] = "f" * 64
        candidate["raw_record"]["payload_sha256"] = "f" * 64
        candidate["admission_receipt"]["raw_artifact_sha256"] = "f" * 64
        candidate["admission_receipt"]["payload_sha256"] = "f" * 64
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        result = validate_admission_fixture(
            self.documents,
            copy.deepcopy(ROUTE_AUTHORITY),
            raw,
            authority,
            candidate,
        )
        self.assertEqual(result["reason_code"], "RAW_OR_PAYLOAD_HASH_MISMATCH")

    def test_empty_receipt_id_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["admission_receipt"]["receipt_id"] = ""
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "RECEIPT_IDENTIFIER_INVALID")

    def test_integer_admission_id_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["admission_receipt"]["admission_id"] = 1
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "ADMISSION_IDENTIFIER_INVALID")

    def test_active_package_alias_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["authority_bundle"]["plan_id"] = "active-g1-plan"
        self.assertEqual(self.validate(candidate)["reason_code"], "FORBIDDEN_ALIAS")

    def test_application_support_alias_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["authority_bundle"]["plan_id"] = "/Users/wt/Library/Application Support/package"
        self.assertEqual(self.validate(candidate)["reason_code"], "FORBIDDEN_ALIAS")

    def test_unknown_candidate_key_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["accept"] = True
        self.assertEqual(
            self.validate(candidate)["reason_code"], "ADMISSION_CANDIDATE_SCHEMA_INVALID"
        )

    def test_receipt_permission_escalation_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["admission_receipt"]["permission"] = "ALLOWED"
        candidate["admission_receipt"]["action"] = "EXECUTE"
        candidate["admission_receipt"]["max_risk"] = 1
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "RECEIPT_BINDING_MISMATCH")

    def test_boolean_is_not_zero_risk_integer(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["admission_receipt"]["max_risk"] = False
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "RECEIPT_MAX_RISK_INVALID")

    def test_available_at_cannot_use_event_clock(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["raw_record"]["available_at"] = candidate["raw_record"]["event_time"]
        self.assertEqual(
            self.validate(candidate)["reason_code"], "AVAILABLE_AT_NOT_CONSERVATIVE_MAX"
        )

    def test_future_row_rejected(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["coverage_proof"]["decision_at"] = "2024-06-02T00:00:02Z"
        candidate["coverage_proof"]["evidence_available_at"] = "2024-06-02T00:00:01Z"
        candidate["authority_bundle"]["created_at"] = "2024-06-02T00:00:01Z"
        candidate["authority_bundle"]["bundle_sha256"] = independent_digest(
            "pitar1/synthetic-authority-bundle/v1",
            candidate["authority_bundle"],
            "bundle_sha256",
        )
        candidate["admission_receipt"]["bundle_sha256"] = candidate["authority_bundle"][
            "bundle_sha256"
        ]
        candidate["admission_receipt"]["decision_at"] = "2024-06-02T00:00:02Z"
        candidate["admission_receipt"]["receipt_sha256"] = independent_digest(
            "pitar1/synthetic-admission-receipt/v1",
            candidate["admission_receipt"],
            "receipt_sha256",
        )
        self.assertEqual(self.validate(candidate)["reason_code"], "FUTURE_ROW")

    def test_event_cannot_be_after_its_availability(self) -> None:
        candidate = copy.deepcopy(self.clean)
        candidate["raw_record"]["event_time"] = "2024-06-04T00:00:00Z"
        self.assertEqual(
            self.validate(candidate)["reason_code"], "EVENT_AFTER_AVAILABILITY"
        )


class RevisionCoverageChronologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = make_revision_row(
            event_id="pitar1.synthetic-event.revision.initial",
            revision_id="pitar1.synthetic-revision.initial",
            ordinal=0,
            supersedes=None,
            operation="INITIAL",
            available_at="2024-06-01T00:00:03Z",
            source_sequence=1,
        )
        self.correction = make_revision_row(
            event_id="pitar1.synthetic-event.revision.correction",
            revision_id="pitar1.synthetic-revision.correction",
            ordinal=1,
            supersedes="pitar1.synthetic-revision.initial",
            operation="CORRECT",
            available_at="2024-06-02T00:00:03Z",
            source_sequence=2,
        )

    def test_append_only_revision_and_replay_order(self) -> None:
        result = validate_revision_fixture(
            [self.correction, self.initial], "2024-06-03T00:00:00Z"
        )
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertEqual(
            result["details"]["replay_order"],
            [
                "pitar1.synthetic-event.revision.initial",
                "pitar1.synthetic-event.revision.correction",
            ],
        )

    def test_exact_duplicate_is_idempotent(self) -> None:
        result = validate_revision_fixture(
            [self.initial, copy.deepcopy(self.initial)], "2024-06-03T00:00:00Z"
        )
        self.assertEqual(result["details"]["input_count"], 2)
        self.assertEqual(result["details"]["unique_effect_count"], 1)

    def test_same_identity_different_payload_quarantines_and_suspends(self) -> None:
        conflict = copy.deepcopy(self.initial)
        conflict["payload_sha256"] = "f" * 64
        result = validate_revision_fixture(
            [self.initial, conflict], "2024-06-03T00:00:00Z"
        )
        self.assertEqual(result["status"], "SUSPEND")
        self.assertEqual(result["reason_code"], "IDENTITY_PAYLOAD_CONFLICT")
        self.assertTrue(result["details"]["denominator_retained"])

    def test_late_revision_not_backfilled(self) -> None:
        result = validate_revision_fixture(
            [self.initial, self.correction], "2024-06-01T12:00:00Z"
        )
        self.assertEqual(
            result["details"]["visible_event_ids"],
            ["pitar1.synthetic-event.revision.initial"],
        )

    def test_revision_chain_gap_rejected(self) -> None:
        bad = copy.deepcopy(self.correction)
        bad["revision_ordinal"] = 2
        result = validate_revision_fixture(
            [self.initial, bad], "2024-06-03T00:00:00Z"
        )
        self.assertEqual(result["reason_code"], "REVISION_ORDINAL_GAP")

    def test_revision_fork_quarantines_and_suspends(self) -> None:
        fork = copy.deepcopy(self.correction)
        fork["event_id"] = "pitar1.synthetic-event.revision.fork"
        fork["source_event_id"] = "pitar1.synthetic-event.revision.fork.source"
        fork["revision_id"] = "pitar1.synthetic-revision.fork"
        fork["source_sequence"] = 3
        fork["payload_sha256"] = hashlib.sha256(b"fork payload").hexdigest()
        result = validate_revision_fixture(
            [self.initial, self.correction, fork], "2024-06-03T00:00:00Z"
        )
        self.assertEqual(result["status"], "SUSPEND")
        self.assertEqual(result["reason_code"], "REVISION_FORK_CONFLICT")
        self.assertTrue(result["details"]["quarantine"])

    def test_gap_and_unknown_are_typed_and_retained(self) -> None:
        gap = copy.deepcopy(self.initial)
        gap["coverage_state"] = "SEQUENCE_GAP"
        result = validate_revision_fixture([gap], "2024-06-03T00:00:00Z")
        self.assertEqual(result["status"], "SUSPEND")
        self.assertEqual(result["details"]["denominator_count"], 1)
        self.assertTrue(result["details"]["denominator_retained"])

    def test_bool_is_not_source_sequence_integer(self) -> None:
        bad = copy.deepcopy(self.initial)
        bad["source_sequence"] = True
        result = validate_revision_fixture([bad], "2024-06-03T00:00:00Z")
        self.assertEqual(result["reason_code"], "ROW_SOURCE_SEQUENCE_INVALID")

    def test_chronology_half_open_roles(self) -> None:
        windows = [
            {
                "window_id": "pitar1.window.engineering.v1",
                "start_inclusive": "2024-01-01T00:00:00Z",
                "end_exclusive": "2024-02-01T00:00:00Z",
                "role": "ENGINEERING_REPLAY_QA_ONLY",
                "accessed": True,
            },
            {
                "window_id": "pitar1.window.reserved.v1",
                "start_inclusive": "2024-03-01T00:00:00Z",
                "end_exclusive": "2024-04-01T00:00:00Z",
                "role": "CALIBRATION_RESERVED_UNSEEN",
                "accessed": False,
            },
        ]
        result = validate_chronology_fixture(windows)
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")

    def test_seen_window_cannot_become_reserved(self) -> None:
        windows = [
            {
                "window_id": "pitar1.window.consumed.v1",
                "start_inclusive": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-02-01T00:00:00Z",
                "role": "ONE_TIME_HOLDOUT_RESERVED_UNSEEN",
                "accessed": False,
            }
        ]
        self.assertEqual(
            validate_chronology_fixture(windows)["reason_code"],
            "CONSUMED_WINDOW_REUSE",
        )

    def test_isolated_scope_overlap_rejected(self) -> None:
        windows = [
            {
                "window_id": "pitar1.window.isolated-overlap.v1",
                "start_inclusive": "2026-07-24T00:00:00Z",
                "end_exclusive": "2026-07-25T00:00:00Z",
                "role": "ENGINEERING_REPLAY_QA_ONLY",
                "accessed": False,
            }
        ]
        self.assertEqual(
            validate_chronology_fixture(windows)["reason_code"],
            "ISOLATED_SCOPE_OVERLAP",
        )

    def test_overlapping_windows_rejected(self) -> None:
        windows = [
            {
                "window_id": "pitar1.window.a.v1",
                "start_inclusive": "2024-01-01T00:00:00Z",
                "end_exclusive": "2024-03-01T00:00:00Z",
                "role": "ENGINEERING_REPLAY_QA_ONLY",
                "accessed": False,
            },
            {
                "window_id": "pitar1.window.b.v1",
                "start_inclusive": "2024-02-01T00:00:00Z",
                "end_exclusive": "2024-04-01T00:00:00Z",
                "role": "DEVELOPMENT_SEEN",
                "accessed": False,
            },
        ]
        self.assertEqual(
            validate_chronology_fixture(windows)["reason_code"],
            "CHRONOLOGY_OVERLAP",
        )


class InterfaceComparisonAndD0Tests(unittest.TestCase):
    def test_adapter_interface_clean(self) -> None:
        result = validate_adapter_fixture(make_adapter_fixture())
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertFalse(result["details"]["runtime_executed"])

    def test_adapter_forbidden_operation_rejected(self) -> None:
        fixture = make_adapter_fixture()
        fixture["observed_operations"] = ["NETWORK_ACCESS"]
        self.assertEqual(
            validate_adapter_fixture(fixture)["reason_code"],
            "ADAPTER_FORBIDDEN_OPERATION",
        )

    def test_adapter_runtime_escalation_rejected(self) -> None:
        fixture = make_adapter_fixture()
        fixture["runtime_executed"] = True
        self.assertEqual(
            validate_adapter_fixture(fixture)["reason_code"],
            "ADAPTER_RUNTIME_OR_PERMISSION_ESCALATION",
        )

    def test_adapter_boolean_is_not_zero_risk_integer(self) -> None:
        fixture = make_adapter_fixture()
        fixture["max_risk"] = False
        self.assertEqual(
            validate_adapter_fixture(fixture)["reason_code"],
            "ADAPTER_MAX_RISK_INVALID",
        )

    def test_replay_sort_key_is_exact(self) -> None:
        fixture = make_adapter_fixture()
        fixture["sort_key"] = ["event_time", "source_sequence", "event_id"]
        self.assertEqual(
            validate_adapter_fixture(fixture)["reason_code"], "REPLAY_ORDER_MISMATCH"
        )

    def test_replay_receipt_chain_clean(self) -> None:
        first = make_replay_receipt(
            receipt_id="pitar1.synthetic-replay-receipt.first.v1",
            prior_digest=None,
            first_event_id="pitar1.synthetic-event.first.v1",
            last_event_id="pitar1.synthetic-event.second.v1",
            first_sequence=1,
            last_sequence=2,
        )
        second = make_replay_receipt(
            receipt_id="pitar1.synthetic-replay-receipt.second.v1",
            prior_digest=first["replay_receipt_sha256"],
            first_event_id="pitar1.synthetic-event.third.v1",
            last_event_id="pitar1.synthetic-event.fourth.v1",
            first_sequence=3,
            last_sequence=4,
        )
        result = validate_replay_receipt_fixture([first, second])
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertFalse(result["details"]["runtime_executed"])

    def test_replay_receipt_chain_break_rejected(self) -> None:
        first = make_replay_receipt(
            receipt_id="pitar1.synthetic-replay-receipt.first.v1",
            prior_digest=None,
            first_event_id="pitar1.synthetic-event.first.v1",
            last_event_id="pitar1.synthetic-event.second.v1",
            first_sequence=1,
            last_sequence=2,
        )
        second = make_replay_receipt(
            receipt_id="pitar1.synthetic-replay-receipt.second.v1",
            prior_digest="f" * 64,
            first_event_id="pitar1.synthetic-event.third.v1",
            last_event_id="pitar1.synthetic-event.fourth.v1",
            first_sequence=3,
            last_sequence=4,
        )
        self.assertEqual(
            validate_replay_receipt_fixture([first, second])["reason_code"],
            "REPLAY_RECEIPT_CHAIN_BROKEN",
        )

    def test_aggregate_bar_double_touch_is_ambiguous(self) -> None:
        fixture = {
            "bar_closed_and_admitted": True,
            "ohlc_extrema_visible": True,
            "finer_grained_source_admitted": False,
            "upper_barrier_touched": True,
            "lower_barrier_touched": True,
            "declared_outcome": "AMBIGUOUS_OR_CENSORED",
            "mfe_mae_used_as_input": False,
        }
        result = validate_barrier_fixture(fixture)
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")

    def test_favorable_first_assumption_rejected(self) -> None:
        fixture = {
            "bar_closed_and_admitted": True,
            "ohlc_extrema_visible": True,
            "finer_grained_source_admitted": False,
            "upper_barrier_touched": True,
            "lower_barrier_touched": True,
            "declared_outcome": "UPPER_FIRST",
            "mfe_mae_used_as_input": False,
        }
        self.assertEqual(
            validate_barrier_fixture(fixture)["reason_code"],
            "FAVORABLE_FIRST_ASSUMPTION",
        )

    def test_full_bar_extrema_before_admission_rejected(self) -> None:
        fixture = {
            "bar_closed_and_admitted": False,
            "ohlc_extrema_visible": True,
            "finer_grained_source_admitted": False,
            "upper_barrier_touched": False,
            "lower_barrier_touched": False,
            "declared_outcome": "NEITHER",
            "mfe_mae_used_as_input": False,
        }
        self.assertEqual(
            validate_barrier_fixture(fixture)["reason_code"],
            "FULL_BAR_FUTURE_LEAKAGE",
        )

    def test_four_policy_equal_information_clean(self) -> None:
        result = validate_comparison_fixture(make_comparison_fixture())
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertEqual(result["details"]["policy_count"], 4)
        self.assertFalse(result["details"]["scoring_executed"])

    def test_unequal_information_rejected(self) -> None:
        fixture = make_comparison_fixture()
        fixture["information_digest_by_policy"]["SINGLE_PATH"] = "f" * 64
        self.assertEqual(
            validate_comparison_fixture(fixture)["reason_code"],
            "UNEQUAL_POLICY_INFORMATION",
        )

    def test_post_outcome_mfe_cannot_be_policy_input(self) -> None:
        fixture = make_comparison_fixture()
        fixture["policy_input_fields"].append("mfe_post_outcome_only")
        self.assertEqual(
            validate_comparison_fixture(fixture)["reason_code"], "POST_OUTCOME_LEAKAGE"
        )

    def test_real_scoring_and_permission_escalation_rejected(self) -> None:
        fixture = make_comparison_fixture()
        fixture["real_data"] = True
        fixture["scoring_executed"] = True
        fixture["permission"] = "ALLOWED"
        self.assertEqual(
            validate_comparison_fixture(fixture)["reason_code"],
            "EVALUATION_OR_PERMISSION_ESCALATION",
        )

    def test_comparison_boolean_is_not_zero_risk_integer(self) -> None:
        fixture = make_comparison_fixture()
        fixture["max_risk"] = False
        self.assertEqual(
            validate_comparison_fixture(fixture)["reason_code"],
            "COMPARISON_MAX_RISK_INVALID",
        )

    def test_complete_four_policy_trajectory_schema_without_scoring(self) -> None:
        result = validate_trajectory_fixture(make_trajectory_rows())
        self.assertEqual(result["status"], "VALID_E0_SYNTHETIC_FIXTURE")
        self.assertEqual(result["details"]["row_count"], 4)
        self.assertFalse(result["details"]["scoring_executed"])

    def test_trajectory_missing_policy_denominator_rejected(self) -> None:
        rows = make_trajectory_rows()
        rows.pop()
        self.assertEqual(
            validate_trajectory_fixture(rows)["reason_code"],
            "TRAJECTORY_POLICY_DENOMINATOR_INCOMPLETE",
        )

    def test_negative_trajectory_count_rejected(self) -> None:
        rows = make_trajectory_rows()
        rows[0]["entry_count"] = -1
        self.assertEqual(
            validate_trajectory_fixture(rows)["reason_code"], "TRAJECTORY_COUNT_INVALID"
        )

    def test_current_d0_candidate_remains_wait_data(self) -> None:
        inventory = json.loads(
            (ROOT / "config/pit_authority_replay.source_inventory.v1.json").read_text()
        )
        result = validate_d0_candidate(inventory["d0_plan_candidate"])
        self.assertEqual(result["status"], "WAIT_DATA")
        self.assertEqual(result["permission"], "DENIED")
        self.assertTrue(result["details"]["blocking_unknowns"])

    def test_d0_ready_with_unknowns_rejected(self) -> None:
        inventory = json.loads(
            (ROOT / "config/pit_authority_replay.source_inventory.v1.json").read_text()
        )
        candidate = inventory["d0_plan_candidate"]
        candidate["status"] = "READY_FOR_EXTERNAL_D0_REVIEW"
        self.assertEqual(
            validate_d0_candidate(candidate)["reason_code"], "D0_READY_WITH_UNKNOWNS"
        )

    def test_d0_cap_escalation_rejected(self) -> None:
        inventory = json.loads(
            (ROOT / "config/pit_authority_replay.source_inventory.v1.json").read_text()
        )
        candidate = inventory["d0_plan_candidate"]
        candidate["maximum_concurrency"] = 2
        self.assertEqual(
            validate_d0_candidate(candidate)["reason_code"], "D0_CAP_EXCEEDED"
        )

    def test_d0_alias_rejected(self) -> None:
        inventory = json.loads(
            (ROOT / "config/pit_authority_replay.source_inventory.v1.json").read_text()
        )
        candidate = inventory["d0_plan_candidate"]
        candidate["output_root"] = "/Users/wt/Library/Application Support/active-g1"
        self.assertEqual(
            validate_d0_candidate(candidate)["reason_code"], "D0_FORBIDDEN_ALIAS"
        )


class PurityAndTotalityTests(unittest.TestCase):
    def test_validator_has_no_forbidden_runtime_import_or_io_calls(self) -> None:
        source_path = ROOT / "trade_system/pit_authority_replay_contract_v1.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden_modules = {
            "os",
            "pathlib",
            "socket",
            "requests",
            "urllib",
            "subprocess",
            "random",
            "secrets",
            "time",
        }
        imported: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        self.assertFalse(imported & forbidden_modules)
        self.assertNotIn("open", calls)
        self.assertNotIn("now", calls)
        self.assertNotIn("utcnow", calls)

    def test_public_validators_are_total_over_wrong_shapes(self) -> None:
        wrong_values: list[Any] = [None, True, 1, 1.5, "x", b"x", [], {}, object()]
        for value in wrong_values:
            with self.subTest(value_type=type(value).__name__):
                self.assertIsInstance(
                    validate_pitar1_contract_bundle(value, copy.deepcopy(ROUTE_AUTHORITY)),
                    dict,
                )
                self.assertIsInstance(validate_revision_fixture(value, value), dict)
                self.assertIsInstance(validate_chronology_fixture(value), dict)
                self.assertIsInstance(validate_adapter_fixture(value), dict)
                self.assertIsInstance(validate_comparison_fixture(value), dict)
                self.assertIsInstance(validate_d0_candidate(value), dict)
                self.assertIsInstance(validate_replay_receipt_fixture(value), dict)
                self.assertIsInstance(validate_barrier_fixture(value), dict)
                self.assertIsInstance(validate_trajectory_fixture(value), dict)


if __name__ == "__main__":
    unittest.main()
