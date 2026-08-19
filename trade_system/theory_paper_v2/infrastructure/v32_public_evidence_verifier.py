"""Infrastructure implementation of the V3.2 public-evidence verifier port."""

from __future__ import annotations

from typing import Any, Mapping

from ..application.v32_public_evidence_port import (
    V32PublicEvidenceVerificationError,
)
from .v32_public_market_graph_projection import (
    v32_public_graph_verification_scope_v1,
    verify_v32_public_market_graph_projection_v1,
    verify_v32_verified_graph_dependency_registry_v1,
)
from .v32_public_source_collector import (
    verify_durable_v32_public_component_no_response_failure_v1,
    verify_durable_v32_public_source_qualification,
    verify_v32_public_market_analysis_bundle,
)


class V32InfrastructurePublicEvidenceVerifier:
    """Delegate full reconstruction to the frozen concrete evidence contracts."""

    def verification_scope(self):
        return v32_public_graph_verification_scope_v1()

    def verify_public_market_analysis_bundle(
        self, document: Mapping[str, Any]
    ) -> str:
        try:
            return verify_v32_public_market_analysis_bundle(document)
        except (TypeError, ValueError) as exc:
            raise V32PublicEvidenceVerificationError(
                "V32_PUBLIC_EVIDENCE_ANALYSIS_BUNDLE_INVALID"
            ) from exc

    def replay_durable_public_source_qualification(
        self,
        *,
        store: Any,
        qualification_id: str,
        active_authority: Mapping[str, Any],
    ) -> Any:
        try:
            return verify_durable_v32_public_source_qualification(
                store=store,
                qualification_id=qualification_id,
                active_authority=active_authority,
            )
        except (TypeError, ValueError) as exc:
            raise V32PublicEvidenceVerificationError(
                "V32_PUBLIC_EVIDENCE_SOURCE_QUALIFICATION_INVALID"
            ) from exc

    def replay_durable_component_no_response_failure(
        self,
        *,
        store: Any,
        qualification_id: str,
        component_id: str,
        binding: Mapping[str, str],
    ) -> Mapping[str, Any]:
        try:
            return verify_durable_v32_public_component_no_response_failure_v1(
                store=store,
                qualification_id=qualification_id,
                component_id=component_id,
                binding=binding,
            )
        except (TypeError, ValueError) as exc:
            raise V32PublicEvidenceVerificationError(
                "V32_PUBLIC_EVIDENCE_COMPONENT_FAILURE_INVALID"
            ) from exc

    def verify_public_market_graph_projection(
        self,
        document: Mapping[str, Any],
        *,
        analysis_bundle: Mapping[str, Any],
        previous_projection: Mapping[str, Any] | None,
    ) -> str:
        try:
            return verify_v32_public_market_graph_projection_v1(
                document,
                analysis_bundle=analysis_bundle,
                previous_projection=previous_projection,
            )
        except (TypeError, ValueError) as exc:
            raise V32PublicEvidenceVerificationError(
                "V32_PUBLIC_EVIDENCE_GRAPH_PROJECTION_INVALID"
            ) from exc

    def verify_graph_dependency_registry(
        self,
        document: Mapping[str, Any],
        *,
        graph_projection: Mapping[str, Any],
        analysis_bundle: Mapping[str, Any],
        previous_projection: Mapping[str, Any] | None,
    ) -> str:
        try:
            return verify_v32_verified_graph_dependency_registry_v1(
                document,
                graph_projection=graph_projection,
                analysis_bundle=analysis_bundle,
                previous_projection=previous_projection,
            )
        except (TypeError, ValueError) as exc:
            raise V32PublicEvidenceVerificationError(
                "V32_PUBLIC_EVIDENCE_GRAPH_REGISTRY_INVALID"
            ) from exc


__all__ = ["V32InfrastructurePublicEvidenceVerifier"]
