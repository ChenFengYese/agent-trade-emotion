"""Infrastructure implementation of the shadow-decision replay port."""

from __future__ import annotations

from typing import Any, Mapping

from ..application.v32_shadow_decision_port import (
    V32ShadowDecisionVerificationError,
)
from .v32_shadow_policy_adapter import (
    verify_v32_replayable_shadow_decision_bundle_v1,
)


class V32InfrastructureShadowDecisionVerifier:
    def verify_replayable_shadow_decision_bundle(
        self, document: Mapping[str, Any], **upstream: Any
    ) -> str:
        try:
            return verify_v32_replayable_shadow_decision_bundle_v1(
                document, **upstream
            )
        except (TypeError, ValueError) as exc:
            raise V32ShadowDecisionVerificationError(
                "V32_SHADOW_DECISION_FULL_REPLAY_INVALID"
            ) from exc


__all__ = ["V32InfrastructureShadowDecisionVerifier"]
