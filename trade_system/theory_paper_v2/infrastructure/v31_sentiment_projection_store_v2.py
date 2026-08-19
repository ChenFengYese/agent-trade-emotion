"""Run-local write-once store for successor sentiment projection support.

This store owns no checkpoint and grants no authority.  It persists only the
source registry, projection receipt, and their embedded binding materials
under one isolated run-root prefix.  Every read requires canonical physical
bytes, and every returned binding has the exact five fields consumed by the
successor commit contract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
    write_once_json,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)


SENTIMENT_PROJECTION_ROOT_V2 = "v31-sentiment-projection-v2"


class V31SentimentProjectionStoreV2Error(ValueError):
    """A successor sentiment artifact was unsafe or physically inconsistent."""


_DOCUMENT_SPECS = {
    "theory_paper_v2_v31_native_sentiment_source_registry": "registry_digest",
    "theory_paper_v2_v31_sentiment_native_projection_receipt": (
        "projection_receipt_digest"
    ),
    "theory_paper_v2_v31_information_datum_binding_material": "material_digest",
    "theory_paper_v2_v31_closed_multitimeframe_evidence_material": (
        "material_digest"
    ),
    "theory_paper_v2_v31_coherence_information_binding_material": (
        "material_digest"
    ),
}


def sentiment_projection_cycle_root_v2(cycle_index: int) -> str:
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31SentimentProjectionStoreV2Error(
            "V31_SENTIMENT_PROJECTION_STORE_CYCLE_INVALID"
        )
    return f"{SENTIMENT_PROJECTION_ROOT_V2}/cycles/{cycle_index:04d}"


def sentiment_source_registry_ref_v2(cycle_index: int) -> str:
    return f"{sentiment_projection_cycle_root_v2(cycle_index)}/source-registry.json"


def sentiment_projection_receipt_ref_v2(cycle_index: int) -> str:
    return (
        f"{sentiment_projection_cycle_root_v2(cycle_index)}/"
        "projection-receipt.json"
    )


def sentiment_material_ref_v2(
    cycle_index: int, *, material_kind: str, material_digest: str
) -> str:
    if material_kind not in {"information", "derived"}:
        raise V31SentimentProjectionStoreV2Error(
            "V31_SENTIMENT_PROJECTION_STORE_MATERIAL_KIND_INVALID"
        )
    if (
        not isinstance(material_digest, str)
        or len(material_digest) != 64
        or any(character not in "0123456789abcdef" for character in material_digest)
    ):
        raise V31SentimentProjectionStoreV2Error(
            "V31_SENTIMENT_PROJECTION_STORE_MATERIAL_DIGEST_INVALID"
        )
    return (
        f"{sentiment_projection_cycle_root_v2(cycle_index)}/materials/"
        f"{material_kind}/{material_digest}.json"
    )


class LocalV31SentimentProjectionStoreV2:
    """Persist immutable sentiment support inside exactly one run root."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, relative_ref: str) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_REF_INVALID"
            )
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or not lexical.parts
            or lexical.parts[0] != SENTIMENT_PROJECTION_ROOT_V2
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_REF_INVALID"
            )
        cursor = self.run_root
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31SentimentProjectionStoreV2Error(
                    "V31_SENTIMENT_PROJECTION_STORE_SYMLINK_FORBIDDEN"
                )
        target = self.run_root.joinpath(*lexical.parts).resolve(strict=False)
        try:
            target.relative_to(self.run_root)
        except ValueError as exc:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_REF_ESCAPE"
            ) from exc
        return target

    @staticmethod
    def _physical_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _verify_document(
        document: Mapping[str, Any], *, digest_field: str
    ) -> str:
        if not isinstance(document, Mapping):
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_DOCUMENT_INVALID"
            )
        schema_id = document.get("schema_id")
        if _DOCUMENT_SPECS.get(str(schema_id)) != digest_field:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_SCHEMA_INVALID"
            )
        try:
            if schema_id == "theory_paper_v2_v31_native_sentiment_source_registry":
                return verify_v31_native_sentiment_source_registry(document)
            return verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_DOCUMENT_INVALID"
            ) from exc

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]:
        semantic = self._verify_document(document, digest_field=digest_field)
        path = self._safe_path(relative_ref)
        try:
            write_once_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_WRITE_ONCE_CONFLICT"
            ) from exc
        durable = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=semantic,
        )
        if dict(durable) != dict(document):
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_READBACK_DRIFT"
            )
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": self._physical_sha256(path),
        }

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        path = self._safe_path(relative_ref)
        try:
            if path.is_symlink() or not path.is_file():
                raise V31SentimentProjectionStoreV2Error(
                    "V31_SENTIMENT_PROJECTION_STORE_DOCUMENT_MISSING"
                )
            document = load_json_strict(path)
            semantic = self._verify_document(
                document, digest_field=digest_field
            )
        except V31SentimentProjectionStoreV2Error:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_DOCUMENT_INVALID"
            ) from exc
        if (
            expected_semantic_digest is not None
            and semantic != expected_semantic_digest
        ):
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_SEMANTIC_DRIFT"
            )
        if path.read_bytes() != canonical_bytes(dict(document)) + b"\n":
            raise V31SentimentProjectionStoreV2Error(
                "V31_SENTIMENT_PROJECTION_STORE_PHYSICAL_DRIFT"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        path = self._safe_path(relative_ref)
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": self._physical_sha256(path),
        }

    def document_exists(self, *, relative_ref: str) -> bool:
        path = self._safe_path(relative_ref)
        return path.is_file() and not path.is_symlink()


__all__ = [
    "LocalV31SentimentProjectionStoreV2",
    "SENTIMENT_PROJECTION_ROOT_V2",
    "V31SentimentProjectionStoreV2Error",
    "sentiment_material_ref_v2",
    "sentiment_projection_cycle_root_v2",
    "sentiment_projection_receipt_ref_v2",
    "sentiment_source_registry_ref_v2",
]
