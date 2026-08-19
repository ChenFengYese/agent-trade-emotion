"""Pure V3.1 application-authority projection for a fully loaded chain.

Infrastructure owns physical replay of the complete authority chronology.  This
module accepts only that loader's complete seven-key result, revalidates the
five standard semantic documents and all typed Q0-Q8 receipts, then returns the
exact five-document contract consumed by Application.

The projection deliberately does not recursively interpret arbitrary evidence
keys as business permissions.  In particular, a Q7 typed AST node such as
``{"kind": "STRING", "value": "NONE_LOCAL_SIMULATION"}`` is data, not an
``external_execution_authority`` field.  Real permission fields remain
fail-closed because the standard V3.1 document validators reconstruct and
validate the five business documents before projection.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from ..v31_experiment_contracts import (
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)
from .v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
    validate_v31_experiment_authorization,
    validate_v31_frozen_experiment_manifest,
    validate_v31_qualification_receipt,
    validate_v31_theory_approval,
)


class V31ApplicationAuthorityProjectionError(ValueError):
    """A complete loader result cannot be projected into Application."""


V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS = (
    "theory_approval",
    "experiment_contract",
    "manifest",
    "authorization_receipt",
    "authority",
)

V31_FULL_LOADER_CHAIN_KEYS = frozenset(
    {
        *V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS,
        "predecessor_authority",
        "qualification_receipts",
    }
)

_GATE_IDS = tuple(f"Q{index}" for index in range(9))


def _validate_complete_loader_shape(loaded_chain: Mapping[str, Any]) -> None:
    if not isinstance(loaded_chain, Mapping) or set(loaded_chain) != (
        V31_FULL_LOADER_CHAIN_KEYS
    ):
        raise V31ApplicationAuthorityProjectionError(
            "V31_APPLICATION_AUTHORITY_FULL_CHAIN_INVALID"
        )
    if any(
        not isinstance(loaded_chain.get(key), Mapping)
        for key in (*V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS, "predecessor_authority")
    ):
        raise V31ApplicationAuthorityProjectionError(
            "V31_APPLICATION_AUTHORITY_FULL_CHAIN_INVALID"
        )
    receipts = loaded_chain.get("qualification_receipts")
    if (
        not isinstance(receipts, Mapping)
        or tuple(receipts) != _GATE_IDS
        or any(not isinstance(receipts.get(gate_id), Mapping) for gate_id in _GATE_IDS)
    ):
        raise V31ApplicationAuthorityProjectionError(
            "V31_APPLICATION_AUTHORITY_QUALIFICATION_CHAIN_INVALID"
        )


def project_v31_application_authority_chain_v2(
    loaded_chain: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate a complete loader result and return its exact five documents.

    This is not an authority loader and performs no file IO.  Callers must first
    use the Infrastructure loader so physical bindings, durable Q6/Q7 evidence,
    and frozen runtime hashes have already passed.  Revalidating semantic
    receipts here prevents a five-document hand-built mapping from masquerading
    as a complete loaded chain.
    """

    _validate_complete_loader_shape(loaded_chain)
    theory_approval = loaded_chain["theory_approval"]
    experiment_contract = loaded_chain["experiment_contract"]
    manifest = loaded_chain["manifest"]
    authorization_receipt = loaded_chain["authorization_receipt"]
    authority = loaded_chain["authority"]
    receipts = loaded_chain["qualification_receipts"]

    try:
        verify_minimal_experiment_contract(experiment_contract)
        validate_v31_theory_approval(theory_approval)
        validate_v31_frozen_experiment_manifest(
            manifest,
            experiment_contract=experiment_contract,
            theory_approval=theory_approval,
        )
        validate_v31_experiment_authorization(
            authorization_receipt,
            manifest=manifest,
            experiment_contract=experiment_contract,
            theory_approval=theory_approval,
        )
        validate_v31_active_authority(
            authority,
            theory_approval=theory_approval,
            manifest=manifest,
            experiment_contract=experiment_contract,
            authorization_receipt=authorization_receipt,
        )
        for gate_id in _GATE_IDS:
            validate_v31_qualification_receipt(
                receipts[gate_id],
                expected_gate_id=gate_id,
                experiment_contract=experiment_contract,
                manifest=manifest,
                theory_approval=theory_approval,
            )
    except (
        V31AuthorizationError,
        V31ExperimentContractError,
        KeyError,
        TypeError,
    ) as exc:
        raise V31ApplicationAuthorityProjectionError(
            "V31_APPLICATION_AUTHORITY_RELATION_OR_PERMISSION_INVALID"
        ) from exc

    return {
        key: copy.deepcopy(dict(loaded_chain[key]))
        for key in V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
    }


__all__ = [
    "V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS",
    "V31_FULL_LOADER_CHAIN_KEYS",
    "V31ApplicationAuthorityProjectionError",
    "project_v31_application_authority_chain_v2",
]
