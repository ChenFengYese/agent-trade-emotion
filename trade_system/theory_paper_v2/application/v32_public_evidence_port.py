"""Application-owned identities and verifier port for V3.2 public evidence."""

from __future__ import annotations

from typing import Any, ContextManager, Mapping, Protocol


ANALYSIS_BUNDLE_SCHEMA_ID = "theory_paper_v32_public_market_analysis_bundle_v1"
ANALYSIS_BUNDLE_DIGEST_FIELD = "public_market_analysis_bundle_digest"
SOURCE_ATTEMPT_SCHEMA_ID = "theory_paper_v32_public_source_attempt_reservation_v1"
SOURCE_ATTEMPT_DIGEST_FIELD = "source_attempt_reservation_digest"
INFORMATION_EVENT_DIGEST_FIELD = "public_source_event_digest"
GRAPH_PROJECTION_SCHEMA_ID = "theory_paper_v32_public_market_graph_projection_v1"
GRAPH_PROJECTION_DIGEST_FIELD = "public_market_graph_projection_digest"
GRAPH_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_graph_dependency_registry_v1"
GRAPH_REGISTRY_DIGEST_FIELD = "graph_dependency_registry_digest"
OKX_PUBLIC_HOST = "openapi.okx.com"
OKX_PUBLIC_BASE_URL = f"https://{OKX_PUBLIC_HOST}"
RAW_BUNDLE_SCHEMA_ID = "theory_paper_v32_okx_public_market_bundle_raw_v1"
# 1.3.0 is the first raw aggregate whose semantic identity is the official
# Global REST hostname ``openapi.okx.com``.  The older 1.2.0/www artifact is
# historical evidence only and is never admitted by the active collector.
RAW_BUNDLE_SCHEMA_VERSION = "1.3.0"


class V32PublicEvidenceVerificationError(ValueError):
    """A concrete public-evidence verifier failed closed."""


class V32PublicEvidenceVerifierPort(Protocol):
    """Full semantic verification implemented by an outer adapter."""

    def verification_scope(self) -> ContextManager[None]: ...

    def verify_public_market_analysis_bundle(
        self, document: Mapping[str, Any]
    ) -> str: ...

    def replay_durable_public_source_qualification(
        self,
        *,
        store: Any,
        qualification_id: str,
        active_authority: Mapping[str, Any],
    ) -> Any: ...

    def replay_durable_component_no_response_failure(
        self,
        *,
        store: Any,
        qualification_id: str,
        component_id: str,
        binding: Mapping[str, str],
    ) -> Mapping[str, Any]: ...

    def verify_public_market_graph_projection(
        self,
        document: Mapping[str, Any],
        *,
        analysis_bundle: Mapping[str, Any],
        previous_projection: Mapping[str, Any] | None,
    ) -> str: ...

    def verify_graph_dependency_registry(
        self,
        document: Mapping[str, Any],
        *,
        graph_projection: Mapping[str, Any],
        analysis_bundle: Mapping[str, Any],
        previous_projection: Mapping[str, Any] | None,
    ) -> str: ...


__all__ = [
    "ANALYSIS_BUNDLE_DIGEST_FIELD",
    "ANALYSIS_BUNDLE_SCHEMA_ID",
    "GRAPH_PROJECTION_DIGEST_FIELD",
    "GRAPH_PROJECTION_SCHEMA_ID",
    "GRAPH_REGISTRY_DIGEST_FIELD",
    "GRAPH_REGISTRY_SCHEMA_ID",
    "INFORMATION_EVENT_DIGEST_FIELD",
    "OKX_PUBLIC_BASE_URL",
    "OKX_PUBLIC_HOST",
    "RAW_BUNDLE_SCHEMA_ID",
    "RAW_BUNDLE_SCHEMA_VERSION",
    "SOURCE_ATTEMPT_DIGEST_FIELD",
    "SOURCE_ATTEMPT_SCHEMA_ID",
    "V32PublicEvidenceVerificationError",
    "V32PublicEvidenceVerifierPort",
]
