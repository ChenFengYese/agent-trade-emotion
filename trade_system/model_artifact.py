"""Machine-readable model dependency and missing-data contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Sequence


class MissingPolicy(str, Enum):
    ABSTAIN = "ABSTAIN"
    DISABLE_FEATURE = "DISABLE_FEATURE"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True)
class SourceRequirement:
    source_id: str
    max_age: timedelta
    missing_policy: MissingPolicy
    fallback_model_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        if self.missing_policy == MissingPolicy.FALLBACK and not self.fallback_model_id:
            raise ValueError("FALLBACK requires fallback_model_id")
        if self.missing_policy != MissingPolicy.FALLBACK and self.fallback_model_id:
            raise ValueError("only FALLBACK may declare fallback_model_id")


@dataclass(frozen=True)
class InputDecision:
    allowed: bool
    reason: str
    disabled_sources: Sequence[str] = ()
    fallback_model_id: Optional[str] = None


@dataclass(frozen=True)
class ModelArtifact:
    model_id: str
    requirements: Sequence[SourceRequirement]

    @classmethod
    def load(cls, path: Path) -> "ModelArtifact":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("cannot load model artifact") from exc
        if not raw.get("model_id") or not isinstance(raw.get("required_sources"), list):
            raise ValueError("model artifact requires model_id and required_sources")
        requirements = []
        for item in raw["required_sources"]:
            requirements.append(SourceRequirement(
                source_id=str(item["source_id"]),
                max_age=timedelta(seconds=float(item["max_age_seconds"])),
                missing_policy=MissingPolicy(item["missing_policy"]),
                fallback_model_id=item.get("fallback_model_id"),
            ))
        return cls(model_id=str(raw["model_id"]), requirements=tuple(requirements))

    def check_inputs(self, *, decision_at: datetime, source_available_at: Dict[str, datetime]) -> InputDecision:
        disabled = []
        for requirement in self.requirements:
            observed = source_available_at.get(requirement.source_id)
            stale = observed is None or decision_at - observed > requirement.max_age
            if not stale:
                continue
            if requirement.missing_policy == MissingPolicy.ABSTAIN:
                return InputDecision(False, "SOURCE_STALE_%s" % requirement.source_id)
            if requirement.missing_policy == MissingPolicy.FALLBACK:
                return InputDecision(False, "FALLBACK_REQUIRED_%s" % requirement.source_id, fallback_model_id=requirement.fallback_model_id)
            disabled.append(requirement.source_id)
        return InputDecision(True, "INPUTS_READY", tuple(disabled))
