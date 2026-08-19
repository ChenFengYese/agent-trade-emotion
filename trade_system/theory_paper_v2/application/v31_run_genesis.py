"""Mechanical initializer for the sole non-executable V3.1 run genesis.

All authority-chain documents and their exact global bytes must already have
been admitted by the active-authority v2.1 loader.  This use case copies those
bytes into the run root, reads every copy back, seals an acyclic genesis
receipt, reads that receipt back, and only then asks the store to initialize
checkpoint 1.2.  It performs no collection, cycle, monitor, account, or order
operation.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    CanonicalContractError,
    loads_json_strict,
    verify_self_digest,
)
from ..domain.v31_run_genesis import (
    GENESIS_SOURCE_SPECS,
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_REF,
    build_v31_run_genesis_receipt,
    checkpoint_genesis_bindings,
    validate_v31_run_genesis_inputs,
    verify_v31_run_genesis_receipt,
)
from .ports import V31ResearchStorePort


class V31RunGenesisInitializationError(ValueError):
    """The initializer failed closed before advancing any cycle."""


def _role_set() -> frozenset[str]:
    return frozenset(spec.role for spec in GENESIS_SOURCE_SPECS)


def _verify_global_bytes(
    *,
    role: str,
    raw_bytes: Any,
    document: Mapping[str, Any],
    global_binding: Mapping[str, Any],
) -> bytes:
    if not isinstance(raw_bytes, bytes):
        raise V31RunGenesisInitializationError(
            f"V31_RUN_GENESIS_SOURCE_BYTES_INVALID:{role}"
        )
    physical_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if physical_sha256 != global_binding.get("physical_sha256"):
        raise V31RunGenesisInitializationError(
            f"V31_RUN_GENESIS_SOURCE_BYTES_DRIFT:{role}"
        )
    try:
        parsed = loads_json_strict(raw_bytes)
    except CanonicalContractError as exc:
        raise V31RunGenesisInitializationError(
            f"V31_RUN_GENESIS_SOURCE_JSON_INVALID:{role}"
        ) from exc
    if parsed != dict(document):
        raise V31RunGenesisInitializationError(
            f"V31_RUN_GENESIS_SOURCE_DOCUMENT_DRIFT:{role}"
        )
    return raw_bytes


def _verify_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    run_id: str,
    expected_bindings: Mapping[str, str],
) -> None:
    if not isinstance(checkpoint, Mapping):
        raise V31RunGenesisInitializationError(
            "V31_RUN_GENESIS_CHECKPOINT_INVALID"
        )
    try:
        verify_self_digest(checkpoint, "checkpoint_digest")
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31RunGenesisInitializationError(
            "V31_RUN_GENESIS_CHECKPOINT_DIGEST_INVALID"
        ) from exc
    if (
        checkpoint.get("schema_id")
        != "theory_paper_v31_research_checkpoint"
        or checkpoint.get("schema_version") != "1.2.0"
        or checkpoint.get("run_id") != run_id
        or checkpoint.get("total_cycles") != 8
        or checkpoint.get("status")
        not in {"READY_FOR_CYCLE", "CYCLE_IN_PROGRESS", "FAILED_CLOSED", "TERMINAL"}
        or checkpoint.get("chat_history_is_authority") is not False
        or checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or checkpoint.get("executable") is not False
        or any(
            checkpoint.get(field) != expected
            for field, expected in expected_bindings.items()
        )
    ):
        raise V31RunGenesisInitializationError(
            "V31_RUN_GENESIS_CHECKPOINT_BINDING_INVALID"
        )


def initialize_v31_run_genesis(
    *,
    store: V31ResearchStorePort,
    created_at: str,
    documents: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
    global_raw_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Initialize the sole V3.1 run root without starting its first cycle.

    Exact re-entry is idempotent.  A changed source byte, document, binding,
    genesis timestamp, or existing checkpoint binding fails closed.  Files
    copied before a write conflict may remain as write-once evidence, but the
    checkpoint call is unreachable until every source and the receipt have
    passed readback verification.
    """

    try:
        roles = _role_set()
        if not isinstance(global_raw_bytes, Mapping) or set(global_raw_bytes) != roles:
            raise V31RunGenesisInitializationError(
                "V31_RUN_GENESIS_SOURCE_BYTE_SET_INVALID"
            )
        run_id = validate_v31_run_genesis_inputs(
            documents=documents, global_bindings=global_bindings
        )

        admitted_bytes: dict[str, bytes] = {}
        local_copy_bindings: dict[str, dict[str, str]] = {}
        for spec in GENESIS_SOURCE_SPECS:
            raw_bytes = _verify_global_bytes(
                role=spec.role,
                raw_bytes=global_raw_bytes[spec.role],
                document=documents[spec.role],
                global_binding=global_bindings[spec.role],
            )
            admitted_bytes[spec.role] = raw_bytes
            local_copy_bindings[spec.role] = {
                "relative_ref": spec.local_ref,
                "schema_id": spec.schema_id,
                "digest_field": spec.digest_field,
                "semantic_digest": str(documents[spec.role][spec.digest_field]),
                "physical_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            }

        # Construct before any write so malformed time or binding input leaves
        # no partial genesis.  Physical readback is still mandatory below.
        receipt = build_v31_run_genesis_receipt(
            created_at=created_at,
            documents=documents,
            global_bindings=global_bindings,
            local_copy_bindings=local_copy_bindings,
        )

        for spec in GENESIS_SOURCE_SPECS:
            raw_bytes = admitted_bytes[spec.role]
            store.write_raw(relative_ref=spec.local_ref, payload=raw_bytes)
            readback = store.read_raw(
                relative_ref=spec.local_ref,
                expected_sha256=local_copy_bindings[spec.role]["physical_sha256"],
            )
            if readback != raw_bytes:
                raise V31RunGenesisInitializationError(
                    f"V31_RUN_GENESIS_COPY_BYTES_DRIFT:{spec.role}"
                )
            _verify_global_bytes(
                role=spec.role,
                raw_bytes=readback,
                document=documents[spec.role],
                global_binding=global_bindings[spec.role],
            )

        store.write_document(
            relative_ref=RUN_GENESIS_REF,
            document=receipt,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
        )
        receipt_readback = store.read_document(
            relative_ref=RUN_GENESIS_REF,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
            expected_semantic_digest=str(receipt[RUN_GENESIS_DIGEST_FIELD]),
        )
        if dict(receipt_readback) != receipt:
            raise V31RunGenesisInitializationError(
                "V31_RUN_GENESIS_RECEIPT_READBACK_DRIFT"
            )
        verify_v31_run_genesis_receipt(
            receipt_readback,
            documents=documents,
            global_bindings=global_bindings,
        )
        receipt_binding = store.artifact_binding(
            relative_ref=RUN_GENESIS_REF,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
            expected_semantic_digest=str(receipt[RUN_GENESIS_DIGEST_FIELD]),
        )
        if (
            receipt_binding.get("relative_ref") != RUN_GENESIS_REF
            or receipt_binding.get("semantic_digest")
            != receipt[RUN_GENESIS_DIGEST_FIELD]
            or not isinstance(receipt_binding.get("physical_sha256"), str)
            or len(str(receipt_binding["physical_sha256"])) != 64
        ):
            raise V31RunGenesisInitializationError(
                "V31_RUN_GENESIS_RECEIPT_PHYSICAL_BINDING_INVALID"
            )

        genesis_bindings = checkpoint_genesis_bindings(
            receipt_readback,
            documents=documents,
            global_bindings=global_bindings,
        )
        checkpoint = store.initialize_checkpoint(
            run_id=run_id,
            total_cycles=8,
            created_at=created_at,
            genesis_bindings=genesis_bindings,
        )
        _verify_checkpoint(
            checkpoint, run_id=run_id, expected_bindings=genesis_bindings
        )
        durable_checkpoint = store.load_checkpoint(run_id=run_id)
        if dict(durable_checkpoint) != dict(checkpoint):
            raise V31RunGenesisInitializationError(
                "V31_RUN_GENESIS_CHECKPOINT_READBACK_DRIFT"
            )
        _verify_checkpoint(
            durable_checkpoint,
            run_id=run_id,
            expected_bindings=genesis_bindings,
        )
        return {
            "run_genesis": dict(receipt_readback),
            "run_genesis_binding": dict(receipt_binding),
            "genesis_bindings": dict(genesis_bindings),
            "checkpoint": dict(durable_checkpoint),
        }
    except V31RunGenesisInitializationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V31RunGenesisInitializationError(
            f"V31_RUN_GENESIS_INITIALIZATION_FAILED:{exc}"
        ) from exc


__all__ = [
    "V31RunGenesisInitializationError",
    "initialize_v31_run_genesis",
]
