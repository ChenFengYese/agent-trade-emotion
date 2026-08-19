"""Versioned source contracts bound to forward-market collection evidence.

The registry is deliberately small: it identifies the public sources required
for the current BTCUSDT research path, rather than serving as a generic data
catalog.  A collection records the registry digest and first observed raw
payload hash for each selected source, so later research can identify the
source contract that was in force without treating the registry as proof that
an endpoint or schema was permanently available.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


FROZEN_SOURCE_REGISTRY = "FROZEN_SOURCE_REGISTRY"


class SourceRegistryError(ValueError):
    pass


def _canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> Tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value) or not all(isinstance(item, str) and item for item in value):
        raise SourceRegistryError("%s must be a %slist of non-empty strings" % (field, "possibly empty " if allow_empty else "non-empty "))
    return tuple(value)


@dataclass(frozen=True)
class SourceContract:
    source_id: str
    venue: str
    instrument_scope: Tuple[str, ...]
    transport: str
    endpoints: Tuple[str, ...]
    channels: Tuple[str, ...]
    schema_version: str
    permission: str
    region_constraints: str
    coverage_semantics: str

    def supports_instrument(self, instrument: str) -> bool:
        return instrument.upper() in self.instrument_scope

    def resolved_channels(self, instrument: str) -> Tuple[str, ...]:
        return tuple(channel.replace("{symbol}", instrument.lower()) for channel in self.channels)


@dataclass(frozen=True)
class SourceRegistry:
    registry_id: str
    schema_version: str
    status: str
    frozen_at: str
    sources: Tuple[SourceContract, ...]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "SourceRegistry":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceRegistryError("cannot load source registry") from exc
        if not isinstance(raw, dict):
            raise SourceRegistryError("source registry must be an object")
        required = ("registry_id", "schema_version", "status", "frozen_at")
        missing = [field for field in required if not isinstance(raw.get(field), str) or not raw[field]]
        if missing:
            raise SourceRegistryError("source registry is missing: %s" % ", ".join(missing))
        if raw["status"] != FROZEN_SOURCE_REGISTRY:
            raise SourceRegistryError("source registry must be frozen")
        try:
            frozen_at = raw["frozen_at"].replace("Z", "+00:00")
            if datetime.fromisoformat(frozen_at).tzinfo is None:
                raise ValueError("timezone is required")
        except (AttributeError, ValueError) as exc:
            raise SourceRegistryError("frozen_at must be an ISO-8601 timestamp with timezone") from exc
        sources_raw = raw["sources"]
        if not isinstance(sources_raw, list) or not sources_raw:
            raise SourceRegistryError("sources must be a non-empty list")
        contracts = []
        seen_ids = set()
        for value in sources_raw:
            if not isinstance(value, dict):
                raise SourceRegistryError("source contract must be an object")
            source_id = value.get("source_id")
            if not isinstance(source_id, str) or not re.fullmatch(r"SRC-[A-Z0-9-]+", source_id):
                raise SourceRegistryError("source_id must match SRC-…")
            if source_id in seen_ids:
                raise SourceRegistryError("source_id must be unique: %s" % source_id)
            seen_ids.add(source_id)
            scalar_fields = ("venue", "transport", "schema_version", "permission", "region_constraints", "coverage_semantics")
            if any(not isinstance(value.get(field), str) or not value[field] for field in scalar_fields):
                raise SourceRegistryError("source %s has incomplete contract metadata" % source_id)
            contracts.append(SourceContract(
                source_id=source_id,
                venue=value["venue"],
                instrument_scope=tuple(item.upper() for item in _string_list(value.get("instrument_scope"), "instrument_scope")),
                transport=value["transport"],
                endpoints=_string_list(value.get("endpoints"), "endpoints"),
                channels=_string_list(value.get("channels"), "channels"),
                schema_version=value["schema_version"],
                permission=value["permission"],
                region_constraints=value["region_constraints"],
                coverage_semantics=value["coverage_semantics"],
            ))
        return cls(
            registry_id=raw["registry_id"],
            schema_version=raw["schema_version"],
            status=raw["status"],
            frozen_at=raw["frozen_at"],
            sources=tuple(contracts),
            sha256=_sha256(raw),
        )

    def selected_sources(self, instrument: str, configured_streams: Iterable[str]) -> Tuple[SourceContract, ...]:
        streams = set(configured_streams)
        selected = tuple(source for source in self.sources if source.supports_instrument(instrument) and streams.intersection(source.resolved_channels(instrument)))
        missing = streams - {channel for source in selected for channel in source.resolved_channels(instrument)}
        if missing:
            raise SourceRegistryError("configured streams absent from source registry: %s" % ",".join(sorted(missing)))
        return selected

    def manifest_binding(self, instrument: str, configured_streams: Iterable[str]) -> Dict[str, Any]:
        selected = self.selected_sources(instrument, configured_streams)
        return {
            "registry_id": self.registry_id,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "source_ids": [source.source_id for source in selected],
            "source_schema_versions": {source.source_id: source.schema_version for source in selected},
        }
