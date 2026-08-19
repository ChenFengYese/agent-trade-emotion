"""Application-owned full replay port for one V3.2 shadow decision bundle."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
)


class V32ShadowDecisionVerificationError(ValueError):
    """Full shadow-policy replay failed closed."""


class V32ShadowDecisionVerifierPort(Protocol):
    def verify_replayable_shadow_decision_bundle(
        self, document: Mapping[str, Any], **upstream: Any
    ) -> str: ...


__all__ = [
    "SHADOW_DECISION_BUNDLE_DIGEST_FIELD",
    "SHADOW_DECISION_BUNDLE_SCHEMA_ID",
    "V32ShadowDecisionVerificationError",
    "V32ShadowDecisionVerifierPort",
]
