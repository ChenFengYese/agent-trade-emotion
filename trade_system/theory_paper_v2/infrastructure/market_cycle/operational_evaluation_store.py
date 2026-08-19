"""Create-once storage for replay-derived V3.3.2 operational evaluation facts.

The store is deliberately not an evaluation owner.  Its only write entrypoint
invokes the authoritative runtime/raw-replay evaluator, then seals those exact
canonical facts with the immutable run, experiment-policy, implementation and
cycle binding needed to identify their source.
"""

from __future__ import annotations

from pathlib import Path
import stat
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...domain.market_cycle.evaluation import OperationalEvaluationFactsV1
from ...domain.market_cycle.evidence import EvidencePolicy
from ...domain.market_cycle.experiment import ExperimentPolicyV1
from ...v32_durable_json import write_once_json
from .operational_evaluation import evaluate_completed_cycle_operationally
from .runtime import MarketCycleRuntime


OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_ID = (
    "agent-trade-emotion.v332-operational-evaluation-package"
)
OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_VERSION = "1.0.0"
_PACKAGE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "binding",
        "evaluation_document_sha256",
        "evaluation_document",
    }
)
_BINDING_FIELDS = frozenset(
    {
        "run_id",
        "run_manifest_identity_sha256",
        "experiment_policy_sha256",
        "implementation_sha256",
        "cycle_id",
    }
)
_MAX_PACKAGE_BYTES = 4 * 1024 * 1024


class OperationalEvaluationStoreError(RuntimeError):
    """One derived package cannot be safely created, confirmed, or loaded."""


class FileOperationalEvaluationStore:
    """Seal and reload one exact replay-derived evaluation per completed cycle."""

    def __init__(self, runtime: MarketCycleRuntime) -> None:
        if not isinstance(runtime, MarketCycleRuntime):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_RUNTIME_INVALID"
            )
        self._runtime = runtime

    def package_path(self, cycle_id: str) -> Path:
        """Return the fixed cycle-owned package path without creating it."""

        # The repository owns cycle-id validation.  Requiring a verified cycle
        # before publishing prevents this presentation helper becoming a second
        # path-admission implementation.
        try:
            self._runtime.service.verify_cycle_read(cycle_id)
        except Exception as exc:
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_CYCLE_INVALID"
            ) from exc
        return (
            self._runtime.repository.root
            / cycle_id
            / "operational-evaluation"
            / "package.json"
        )

    def _binding(self, cycle_id: str) -> dict[str, str]:
        manifest = self._runtime.run_manifest
        policy = self._runtime.experiment_policy
        if (
            not isinstance(policy, ExperimentPolicyV1)
            or manifest.run_id != policy.run_id
            or manifest.experiment_identity != policy.policy_sha256
        ):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_POLICY_BINDING_INVALID"
            )
        return {
            "run_id": manifest.run_id,
            "run_manifest_identity_sha256": manifest.identity_sha256,
            "experiment_policy_sha256": policy.policy_sha256,
            "implementation_sha256": manifest.implementation_sha256,
            "cycle_id": cycle_id,
        }

    @staticmethod
    def _package(
        facts: OperationalEvaluationFactsV1, *, binding: Mapping[str, str]
    ) -> dict[str, Any]:
        evaluation = facts.to_dict()
        return {
            "schema_id": OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_ID,
            "schema_version": OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_VERSION,
            "binding": dict(binding),
            "evaluation_document_sha256": canonical_digest(evaluation),
            "evaluation_document": evaluation,
        }

    @staticmethod
    def _read_package(
        path: Path, *, expected_binding: Mapping[str, str]
    ) -> dict[str, Any]:
        try:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size < 2
                or metadata.st_size > _MAX_PACKAGE_BYTES
            ):
                raise OSError("unsafe package file")
            raw = path.read_bytes()
            value = loads_json_strict(raw)
        except (OSError, ValueError, FileNotFoundError) as exc:
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_PACKAGE_UNREADABLE"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _PACKAGE_FIELDS
            or canonical_bytes(value) + b"\n" != raw
            or value.get("schema_id") != OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_ID
            or value.get("schema_version")
            != OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_VERSION
            or not isinstance(value.get("binding"), Mapping)
            or frozenset(value["binding"]) != _BINDING_FIELDS
            or dict(value["binding"]) != dict(expected_binding)
            or not isinstance(value.get("evaluation_document"), Mapping)
            or value.get("evaluation_document_sha256")
            != canonical_digest(value["evaluation_document"])
        ):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_PACKAGE_BINDING_INVALID"
            )
        evaluation = value["evaluation_document"]
        payload = evaluation.get("payload")
        run_identity = payload.get("run_identity") if isinstance(payload, Mapping) else None
        if (
            evaluation.get("schema_id")
            != "agent-trade-emotion.v332-operational-evaluation-facts"
            or evaluation.get("schema_version") != "1.0.0"
            or not isinstance(payload, Mapping)
            or evaluation.get("payload_sha256") != canonical_digest(payload)
            or payload.get("cycle_id") != expected_binding["cycle_id"]
            or not isinstance(run_identity, Mapping)
            or run_identity.get("run_id") != expected_binding["run_id"]
            or run_identity.get("run_manifest_identity_sha256")
            != expected_binding["run_manifest_identity_sha256"]
            or run_identity.get("implementation_sha256")
            != expected_binding["implementation_sha256"]
        ):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_DOCUMENT_BINDING_INVALID"
            )
        return dict(value)

    @staticmethod
    def _confirm_existing_request(
        package: Mapping[str, Any],
        *,
        evaluation_id: str,
        evidence_policy: EvidencePolicy,
    ) -> None:
        evaluation = package.get("evaluation_document")
        payload = evaluation.get("payload") if isinstance(evaluation, Mapping) else None
        policy_binding = (
            payload.get("policy_binding") if isinstance(payload, Mapping) else None
        )
        if (
            not isinstance(payload, Mapping)
            or payload.get("evaluation_id") != evaluation_id
        ):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_ID_WRITE_ONCE_CONFLICT"
            )
        if (
            not isinstance(evidence_policy, EvidencePolicy)
            or not isinstance(policy_binding, Mapping)
            or policy_binding.get("sha256")
            != canonical_digest(evidence_policy.to_dict())
        ):
            raise OperationalEvaluationStoreError(
                "OPERATIONAL_EVALUATION_EVIDENCE_POLICY_MISMATCH"
            )

    def evaluate_and_seal(
        self,
        *,
        cycle_id: str,
        evaluation_id: str,
        evidence_policy: EvidencePolicy,
    ) -> dict[str, Any]:
        """Seal first replay at controller time, or return its validated winner."""

        with self._runtime.mutation_guard():
            with self._runtime.repository.locked(cycle_id):
                binding = self._binding(cycle_id)
                path = self.package_path(cycle_id)
                try:
                    path.lstat()
                except FileNotFoundError:
                    pass
                else:
                    persisted = self._read_package(path, expected_binding=binding)
                    self._confirm_existing_request(
                        persisted,
                        evaluation_id=evaluation_id,
                        evidence_policy=evidence_policy,
                    )
                    return persisted

                evaluated_at = self._runtime.controller_state.trusted_now()
                facts = evaluate_completed_cycle_operationally(
                    runtime=self._runtime,
                    cycle_id=cycle_id,
                    evaluation_id=evaluation_id,
                    evaluated_at=evaluated_at,
                    evidence_policy=evidence_policy,
                )
                package = self._package(facts, binding=binding)
                try:
                    write_once_json(path, package)
                except (CanonicalContractError, OSError) as exc:
                    raise OperationalEvaluationStoreError(
                        "OPERATIONAL_EVALUATION_PACKAGE_WRITE_ONCE_CONFLICT"
                    ) from exc
                persisted = self._read_package(path, expected_binding=binding)
                if canonical_bytes(persisted) != canonical_bytes(package):
                    raise OperationalEvaluationStoreError(
                        "OPERATIONAL_EVALUATION_PACKAGE_READBACK_MISMATCH"
                    )
                return persisted

    def load(self, cycle_id: str) -> dict[str, Any]:
        """Load and revalidate the one package already sealed for a cycle."""

        with self._runtime.repository.locked(cycle_id):
            binding = self._binding(cycle_id)
            return self._read_package(
                self.package_path(cycle_id), expected_binding=binding
            )


__all__ = [
    "OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_ID",
    "OPERATIONAL_EVALUATION_PACKAGE_SCHEMA_VERSION",
    "FileOperationalEvaluationStore",
    "OperationalEvaluationStoreError",
]
