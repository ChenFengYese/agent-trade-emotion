"""Write-once, live-produced feature artifacts for M5 shadow comparison.

The observer consumes only an availability record that has already been
persisted by the public collector.  It never opens an order, mutates raw
evidence, or treats a partial artifact as valid shadow evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .binance import CaptureResult
from .episode_policy import EpisodePolicy
from .pipeline import FeaturePipeline


class LiveShadowError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class LiveFeatureArtifact:
    path: str
    sha256: str
    feature_rows: int
    feature_versions: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "SEALED",
            "path": self.path,
            "sha256": self.sha256,
            "feature_rows": self.feature_rows,
            "feature_versions": list(self.feature_versions),
        }


class LiveFeatureObserver:
    """FeaturePipeline observer that stages rows until a qualified terminal run.

    The final path must be inside the collection Evidence Store and outside its
    raw/availability trees.  A process crash or unqualified collection leaves
    only a ``.partial`` file, which is intentionally not referenced by any
    collection manifest and cannot be consumed by the verifier.
    """

    def __init__(self, output_path: Path, *, evidence_root: Path, episode_policy: Optional[EpisodePolicy] = None) -> None:
        root = Path(evidence_root).resolve()
        requested = Path(output_path)
        target = requested if requested.is_absolute() else root / requested
        target = target.resolve()
        if not _inside(target, root):
            raise LiveShadowError("live feature output must stay inside the evidence store")
        if any(part in {"raw", "availability", "manifests"} for part in target.relative_to(root).parts):
            raise LiveShadowError("live feature output cannot use raw, availability, or manifests paths")
        if target.suffix != ".ndjson":
            raise LiveShadowError("live feature output must use the .ndjson suffix")
        if target.exists():
            raise LiveShadowError("live feature output already exists: %s" % target)
        self.target = target
        self.partial = target.with_name(target.name + ".partial")
        if self.partial.exists():
            raise LiveShadowError("live feature partial artifact already exists: %s" % self.partial)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.partial.open("x", encoding="utf-8")
        self._pipeline = FeaturePipeline(episode_policy)
        self._rows = 0
        self._feature_versions: set[str] = set()
        self._closed = False

    @property
    def partial_path(self) -> str:
        return str(self.partial)

    def observe(self, result: CaptureResult) -> None:
        if self._closed:
            raise LiveShadowError("live feature observer is already closed")
        if not result.availability_written or result.availability is None:
            return
        availability = result.availability
        row = self._pipeline.process(
            result.raw.event_id,
            availability.availability_kind,
            availability.available_at,
            availability.normalized,
        )
        if row is None:
            return
        self._handle.write(json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._rows += 1
        self._feature_versions.add(row.feature_version)

    def finalize(self) -> LiveFeatureArtifact:
        if self._closed:
            raise LiveShadowError("live feature observer is already closed")
        self._closed = True
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        if self._rows <= 0:
            raise LiveShadowError("qualified collection produced no live feature rows")
        # link(2) is an atomic no-replace publication on the same Evidence
        # Store filesystem.  It prevents a late writer from overwriting a
        # supposedly immutable artifact; only our owned partial is unlinked.
        try:
            os.link(self.partial, self.target)
        except OSError as exc:
            raise LiveShadowError("cannot atomically publish live feature artifact") from exc
        self.partial.unlink()
        return LiveFeatureArtifact(
            path=str(self.target),
            sha256=_sha256_file(self.target),
            feature_rows=self._rows,
            feature_versions=tuple(sorted(self._feature_versions)),
        )

    def abandon(self) -> Dict[str, Any]:
        """Close but deliberately retain an excluded partial artifact."""
        if not self._closed:
            self._closed = True
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
        return {
            "status": "PARTIAL_EXCLUDED",
            "partial_path": str(self.partial),
            "feature_rows": self._rows,
        }


def verify_live_feature_artifact(path: Path, binding: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the immutable artifact fields stored in a collection manifest."""
    if not isinstance(binding, dict) or binding.get("status") != "SEALED":
        raise LiveShadowError("collection has no sealed live feature artifact")
    artifact = Path(path)
    if str(artifact.resolve()) != str(Path(str(binding.get("path", ""))).resolve()):
        raise LiveShadowError("live feature artifact path does not match collection manifest")
    if not artifact.exists():
        raise LiveShadowError("live feature artifact is missing")
    sha256 = _sha256_file(artifact)
    if sha256 != binding.get("sha256"):
        raise LiveShadowError("live feature artifact digest does not match collection manifest")
    count = 0
    versions = set()
    try:
        with artifact.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get("event_id"), str) or not isinstance(row.get("feature_version"), str):
                    raise LiveShadowError("invalid live feature row at line %d" % line_number)
                count += 1
                versions.add(row["feature_version"])
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveShadowError("cannot read live feature artifact") from exc
    if count != binding.get("feature_rows"):
        raise LiveShadowError("live feature row count does not match collection manifest")
    if sorted(versions) != sorted(binding.get("feature_versions", [])):
        raise LiveShadowError("live feature versions do not match collection manifest")
    return {"path": str(artifact), "sha256": sha256, "feature_rows": count, "feature_versions": sorted(versions)}
