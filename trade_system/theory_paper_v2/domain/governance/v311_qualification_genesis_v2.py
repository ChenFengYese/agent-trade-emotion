"""Pure cross-binding between standard V3 authority and run-local genesis."""

from __future__ import annotations

from typing import Any, Mapping

from ..v31_run_genesis import (
    GENESIS_SOURCE_SPECS,
    RUN_GENESIS_DIGEST_FIELD,
    V31RunGenesisError,
    verify_v31_run_genesis_receipt,
)


class V311QualificationGenesisV2Error(ValueError):
    """Qualification genesis does not exactly copy the standard V3 chain."""


_ROLE_TO_CHAIN_KEY = {
    "theory_approval": "theory_approval",
    "experiment_contract": "experiment_contract",
    "experiment_manifest": "manifest",
    "experiment_authorization": "authorization_receipt",
    "current_authority": "authority",
}
_ROLE_TO_BINDING_KEY = dict(_ROLE_TO_CHAIN_KEY)


def v311_qualification_genesis_inputs_v2(
    *,
    qualification_v3_chain: Mapping[str, Any],
    qualification_v3_document_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Translate the standard loader chain to run-genesis role names."""

    if not isinstance(qualification_v3_chain, Mapping) or not isinstance(
        qualification_v3_document_bindings, Mapping
    ):
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_STANDARD_CHAIN_INVALID"
        )
    try:
        documents = {
            role: qualification_v3_chain[chain_key]
            for role, chain_key in _ROLE_TO_CHAIN_KEY.items()
        }
        bindings = {
            role: qualification_v3_document_bindings[binding_key]
            for role, binding_key in _ROLE_TO_BINDING_KEY.items()
        }
    except KeyError as exc:
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_STANDARD_CHAIN_INVALID"
        ) from exc
    if any(not isinstance(value, Mapping) for value in (*documents.values(), *bindings.values())):
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_STANDARD_CHAIN_INVALID"
        )
    return documents, bindings


def verify_v311_qualification_run_genesis_v2(
    *,
    run_genesis: Mapping[str, Any],
    qualification_v3_chain: Mapping[str, Any],
    qualification_v3_document_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify receipt semantics and return exact run-local copy bindings."""

    documents, global_bindings = v311_qualification_genesis_inputs_v2(
        qualification_v3_chain=qualification_v3_chain,
        qualification_v3_document_bindings=qualification_v3_document_bindings,
    )
    try:
        genesis_digest = verify_v31_run_genesis_receipt(
            run_genesis,
            documents=documents,
            global_bindings=global_bindings,
        )
    except (TypeError, ValueError, V31RunGenesisError) as exc:
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_RECEIPT_INVALID"
        ) from exc
    rows = run_genesis.get("genesis_artifacts")
    if not isinstance(rows, list) or len(rows) != len(GENESIS_SOURCE_SPECS):
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_ARTIFACTS_INVALID"
        )
    local_bindings: dict[str, dict[str, str]] = {}
    for spec, row in zip(GENESIS_SOURCE_SPECS, rows, strict=True):
        binding_key = _ROLE_TO_BINDING_KEY[spec.role]
        global_binding = global_bindings[spec.role]
        if (
            not isinstance(row, Mapping)
            or row.get("source_role") != spec.role
            or row.get("global_ref") != global_binding.get("path")
            or row.get("local_ref") != spec.local_ref
            or row.get("schema_id") != spec.schema_id
            or row.get("digest_field") != spec.digest_field
            or row.get("semantic_digest")
            != global_binding.get("semantic_digest")
            or row.get("global_physical_sha256")
            != global_binding.get("physical_sha256")
            or row.get("local_physical_sha256")
            != global_binding.get("physical_sha256")
            or row.get("exact_bytes_copied") is not True
            or qualification_v3_document_bindings[binding_key]
            != global_binding
        ):
            raise V311QualificationGenesisV2Error(
                "V311_QUALIFICATION_GENESIS_ARTIFACTS_INVALID"
            )
        local_bindings[spec.role] = {
            "relative_ref": str(row["local_ref"]),
            "schema_id": str(row["schema_id"]),
            "digest_field": str(row["digest_field"]),
            "semantic_digest": str(row["semantic_digest"]),
            "physical_sha256": str(row["local_physical_sha256"]),
        }
    authority_copy = local_bindings["current_authority"]
    if (
        authority_copy["relative_ref"] != "genesis/current-authority.json"
        or authority_copy["semantic_digest"]
        != qualification_v3_chain["authority"].get("authority_digest")
    ):
        raise V311QualificationGenesisV2Error(
            "V311_QUALIFICATION_GENESIS_AUTHORITY_COPY_INVALID"
        )
    return {
        "run_genesis_digest": genesis_digest,
        "run_id": str(run_genesis["run_id"]),
        "local_copy_bindings": local_bindings,
        "authority_copy_binding": authority_copy,
    }


__all__ = [
    "V311QualificationGenesisV2Error",
    "v311_qualification_genesis_inputs_v2",
    "verify_v311_qualification_run_genesis_v2",
]
