"""Non-destructive cold sidecars for terminal, sealed Evidence Stores.

This is intentionally an archive *copy*, not a retention/deletion mechanism.
It gives future development/holdout collections a verifiable compressed copy
without changing existing raw manifests or removing hot evidence.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .event_store import EventStore, EventStoreError, _canonical_json
from .replay import DeterministicReplay


ARCHIVE_RECEIPT_SCHEMA = "evidence-archive-receipt.v1"
RETIREMENT_PLAN_SCHEMA = "hot-evidence-retirement-plan.v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class EvidenceArchiveError(ValueError):
    """A hot evidence store or archive sidecar fails its immutable contract."""


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _segment_stats(path: Path) -> Tuple[str, int, int]:
    digest = hashlib.sha256()
    byte_count = record_count = 0
    with Path(path).open("rb") as handle:
        for line in handle:
            digest.update(line)
            byte_count += len(line)
            if line.strip():
                record_count += 1
    return digest.hexdigest(), byte_count, record_count


def _load_json(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceArchiveError("cannot load %s" % label) from exc
    if not isinstance(value, dict):
        raise EvidenceArchiveError("%s must be an object" % label)
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise EvidenceArchiveError("path escapes its declared root") from exc


def _resolve_relative(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise EvidenceArchiveError("%s path is missing" % label)
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise EvidenceArchiveError("%s path escapes cold root" % label) from exc
    return candidate


def _collection_terminal(store: EventStore, collection_id: str) -> Dict[str, Any]:
    if not _IDENTIFIER.fullmatch(collection_id):
        raise EvidenceArchiveError("collection_id contains unsupported characters")
    path = store.collection_manifest_root / (collection_id + ".json")
    terminal = _load_json(path, "terminal collection manifest")
    if terminal.get("record_type") != "collection_manifest" or terminal.get("collection_id") != collection_id:
        raise EvidenceArchiveError("terminal collection manifest identity is invalid")
    return terminal


def _validate_hot_collection(store: EventStore, collection_id: str) -> Tuple[Dict[str, Any], List[Any], List[Any], str, str]:
    """Require a terminal, fully sealed, collection-isolated hot store."""
    terminal = _collection_terminal(store, collection_id)
    try:
        audit_valid, audit_issues, audit_digest, raws, availability = store.audit_with_records()
    except (EventStoreError, OSError, ValueError) as exc:
        raise EvidenceArchiveError("cannot audit hot evidence") from exc
    if not audit_valid:
        raise EvidenceArchiveError("hot evidence audit failed: %s" % ", ".join(audit_issues))
    replay_digest = DeterministicReplay.digest_from_records(raws, availability)
    if terminal.get("audit_digest") != audit_digest or terminal.get("replay_digest") != replay_digest:
        raise EvidenceArchiveError("terminal collection digest does not match current hot evidence")
    prefix = collection_id + "-"
    collection_raws = [raw for raw in raws if raw.connection_id.startswith(prefix)]
    if not collection_raws:
        raise EvidenceArchiveError("terminal collection has no raw evidence")
    # A v1 sidecar archives whole NDJSON segments.  Refusing a mixed store is
    # safer than silently including a second collection in one receipt.
    if len(collection_raws) != len(raws):
        raise EvidenceArchiveError("v1 archive requires a collection-isolated evidence store")
    raw_ids = {raw.event_id for raw in collection_raws}
    if len(raw_ids) != len(collection_raws):
        raise EvidenceArchiveError("hot collection has duplicate raw event IDs")
    if len(availability) != len(raw_ids) or {item.event_id for item in availability} != raw_ids:
        raise EvidenceArchiveError("every archived raw event requires exactly one availability record")
    sealed = {path.stem for path in store.manifest_root.glob("*.json")}
    segments = {Path(raw.raw_segment).stem for raw in collection_raws}
    if not segments or not segments.issubset(sealed):
        raise EvidenceArchiveError("collection raw segments are not all sealed")
    return terminal, collection_raws, availability, audit_digest, replay_digest


def _gzip_segment(source: Path, *, cold_root: Path, kind: str) -> Dict[str, Any]:
    source_sha, byte_count, record_count = _segment_stats(source)
    objects = cold_root / "objects" / kind
    objects.mkdir(parents=True, exist_ok=True)
    target = objects / (source_sha + ".ndjson.gz")
    partial = target.with_name(target.name + ".partial")
    stale = sorted(objects.glob("*.partial"))
    if stale:
        raise EvidenceArchiveError("stale archive partial requires operator inspection: %s" % stale[0])
    if target.exists():
        compressed_sha = _sha256_file(target)
    else:
        try:
            with source.open("rb") as source_handle, partial.open("xb") as partial_handle:
                # ``filename`` and ``mtime`` make bytes deterministic for the
                # same input and Python gzip implementation.
                with gzip.GzipFile(filename="", mode="wb", fileobj=partial_handle, mtime=0) as compressed:
                    for block in iter(lambda: source_handle.read(1024 * 1024), b""):
                        compressed.write(block)
                partial_handle.flush()
                os.fsync(partial_handle.fileno())
            try:
                os.link(partial, target)
            except FileExistsError:
                pass
            finally:
                if partial.exists():
                    partial.unlink()
        except OSError as exc:
            # Keep a partial on write failure: it is deliberately not a valid
            # object and a later run must not silently accept it.
            raise EvidenceArchiveError("cannot create compressed archive segment") from exc
        compressed_sha = _sha256_file(target)
    return {
        "kind": kind,
        "source_sha256": source_sha,
        "source_byte_count": byte_count,
        "source_record_count": record_count,
        "compression": "gzip",
        "compression_mtime": 0,
        "cold_path": _relative(target, cold_root),
        "cold_sha256": compressed_sha,
    }


def _write_once(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise EvidenceArchiveError("archive receipt already exists") from exc
    except OSError as exc:
        raise EvidenceArchiveError("cannot write archive receipt") from exc


def archive_sealed_collection(*, store: EventStore, collection_id: str, cold_root: Path, archive_id: str) -> Dict[str, Any]:
    """Create a write-once gzip sidecar without changing hot evidence.

    The EventStore writer lock makes the audit/copy transition atomic with
    respect to compliant EventStore writers.  It is not a claim that a local
    administrator cannot alter files; all later reads re-verify hashes.
    """
    if not _IDENTIFIER.fullmatch(archive_id):
        raise EvidenceArchiveError("archive_id contains unsupported characters")
    cold_root = Path(cold_root)
    with store._writer_lock():
        terminal, _raws, _availability, audit_digest, replay_digest = _validate_hot_collection(store, collection_id)
        raw_paths = sorted(store.raw_root.glob("*.ndjson"))
        availability_paths = sorted(store.availability_root.glob("*.ndjson"))
        # Validation above requires isolated evidence, so every file is part
        # of this collection.  Include both streams in the sidecar seal.
        raw_segments = []
        for path in raw_paths:
            entry = _gzip_segment(path, cold_root=cold_root, kind="raw")
            entry["source_path"] = _relative(path, store.root)
            raw_segments.append(entry)
        availability_segments = []
        for path in availability_paths:
            entry = _gzip_segment(path, cold_root=cold_root, kind="availability")
            entry["source_path"] = _relative(path, store.root)
            availability_segments.append(entry)
    receipt = {
        "record_type": "evidence_archive_receipt",
        "schema_version": ARCHIVE_RECEIPT_SCHEMA,
        "archive_id": archive_id,
        "collection_id": collection_id,
        "source_evidence_root": str(store.root.resolve()),
        "terminal_manifest_path": str((store.collection_manifest_root / (collection_id + ".json")).resolve()),
        "terminal_manifest_sha256": _sha256_file(store.collection_manifest_root / (collection_id + ".json")),
        "collection_result": terminal.get("collection_result"),
        "audit_digest": audit_digest,
        "replay_digest": replay_digest,
        "capture_plan": terminal.get("capture_plan"),
        "source_registry": terminal.get("source_registry"),
        "collector_software": terminal.get("collector_software"),
        "raw_seal": {"segments": raw_segments},
        # Existing EventStore v1 has no availability manifest.  This sidecar
        # is its independent write-once availability seal binding.
        "availability_seal": {"segments": availability_segments},
        "non_destructive": True,
        "retire_hot_copy_supported": False,
    }
    receipt["receipt_sha256"] = _digest(receipt)
    receipt_path = cold_root / "receipts" / (archive_id + ".json")
    _write_once(receipt_path, receipt)
    return dict(receipt, receipt_path=str(receipt_path))


def _verified_receipt(path: Path) -> Dict[str, Any]:
    receipt = _load_json(Path(path), "archive receipt")
    if receipt.get("record_type") != "evidence_archive_receipt" or receipt.get("schema_version") != ARCHIVE_RECEIPT_SCHEMA:
        raise EvidenceArchiveError("archive receipt schema is invalid")
    expected = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not isinstance(expected, str) or expected != _digest(body):
        raise EvidenceArchiveError("archive receipt digest does not match content")
    if receipt.get("non_destructive") is not True or receipt.get("retire_hot_copy_supported") is not False:
        raise EvidenceArchiveError("archive receipt has an unsupported retention claim")
    return receipt


def load_verified_evidence_archive_receipt(path: Path) -> Dict[str, Any]:
    """Return the immutable receipt only after its own digest is verified.

    Role-data builders use this small public API to bind archive identity and
    receipt SHA; cold byte/replay verification remains available separately
    through :func:`verify_evidence_archive`.
    """
    return _verified_receipt(Path(path))


def _decompress_segment(cold_root: Path, entry: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
    if not isinstance(entry, dict) or entry.get("compression") != "gzip" or entry.get("compression_mtime") != 0:
        raise EvidenceArchiveError("archive segment compression contract is invalid")
    path = _resolve_relative(cold_root, entry.get("cold_path"), "archive segment")
    if path.suffix != ".gz" or path.name.endswith(".partial") or not path.is_file():
        raise EvidenceArchiveError("archive segment is missing or not finalized")
    if _sha256_file(path) != entry.get("cold_sha256"):
        raise EvidenceArchiveError("compressed archive segment checksum mismatch")
    try:
        with gzip.open(path, "rb") as handle:
            data = handle.read()
    except (OSError, EOFError) as exc:
        raise EvidenceArchiveError("cannot decompress archive segment") from exc
    digest = hashlib.sha256(data).hexdigest()
    records = sum(1 for line in data.splitlines() if line.strip())
    if digest != entry.get("source_sha256") or len(data) != entry.get("source_byte_count") or records != entry.get("source_record_count"):
        raise EvidenceArchiveError("decompressed archive segment does not match its source seal")
    return data, entry


def _json_lines(data: bytes, label: str) -> Iterable[Dict[str, Any]]:
    for index, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceArchiveError("invalid JSON in archived %s at line %d" % (label, index)) from exc
        if not isinstance(value, dict):
            raise EvidenceArchiveError("archived %s record must be an object" % label)
        yield value


def _cold_records(receipt: Dict[str, Any], cold_root: Path) -> Tuple[List[Any], List[Any]]:
    raw_entries = receipt.get("raw_seal", {}).get("segments")
    availability_entries = receipt.get("availability_seal", {}).get("segments")
    if not isinstance(raw_entries, list) or not raw_entries or not isinstance(availability_entries, list) or not availability_entries:
        raise EvidenceArchiveError("archive receipt is missing raw or availability seals")
    raw_values: List[Dict[str, Any]] = []
    availability_values: List[Dict[str, Any]] = []
    for entry in raw_entries:
        if entry.get("kind") != "raw":
            raise EvidenceArchiveError("raw seal contains a non-raw segment")
        data, _ = _decompress_segment(cold_root, entry)
        raw_values.extend(_json_lines(data, "raw"))
    for entry in availability_entries:
        if entry.get("kind") != "availability":
            raise EvidenceArchiveError("availability seal contains a non-availability segment")
        data, _ = _decompress_segment(cold_root, entry)
        availability_values.extend(_json_lines(data, "availability"))
    try:
        raws = [EventStore._raw_from_dict(item) for item in raw_values]
        availability = [EventStore._availability_from_dict(item) for item in availability_values]
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceArchiveError("archived record schema is invalid") from exc
    raws.sort(key=lambda item: item.capture_seq)
    availability.sort(key=lambda item: (item.available_at, item.derived_at, item.event_id, item.schema_version))
    return raws, availability


def _audit_digest(raws: Sequence[Any], availability: Sequence[Any]) -> str:
    digest = hashlib.sha256()
    for raw in raws:
        digest.update(_canonical_json(raw.to_dict()).encode("utf-8"))
    for record in availability:
        digest.update(_canonical_json(record.to_dict()).encode("utf-8"))
    return digest.hexdigest()


def verify_evidence_archive(receipt_path: Path) -> Dict[str, Any]:
    """Verify cold bytes, parsed records and deterministic replay without hot I/O."""
    receipt_path = Path(receipt_path)
    receipt = _verified_receipt(receipt_path)
    raws, availability = _cold_records(receipt, receipt_path.parent.parent)
    audit_digest = _audit_digest(raws, availability)
    replay_digest = DeterministicReplay.digest_from_records(raws, availability)
    if audit_digest != receipt.get("audit_digest") or replay_digest != receipt.get("replay_digest"):
        raise EvidenceArchiveError("cold archive audit or replay digest does not match receipt")
    return {
        "archive_id": receipt["archive_id"], "collection_id": receipt["collection_id"],
        "valid": True, "audit_digest": audit_digest, "replay_digest": replay_digest,
        "raw_records": len(raws), "availability_records": len(availability),
        "non_destructive": True,
    }


def load_cold_evidence_records(receipt_path: Path) -> Tuple[List[Any], List[Any], Dict[str, Any]]:
    """Read verified cold records without requiring a hot EventStore.

    This is the cold equivalent of the record inputs accepted by
    ``DeterministicReplay.events_from_records``.  It verifies compressed
    object bytes, parsed schemas, audit/replay digests and the immutable
    receipt before returning anything, so callers never replay an unchecked
    gzip sidecar as evidence.
    """
    receipt_path = Path(receipt_path)
    receipt = _verified_receipt(receipt_path)
    raws, availability = _cold_records(receipt, receipt_path.parent.parent)
    audit_digest = _audit_digest(raws, availability)
    replay_digest = DeterministicReplay.digest_from_records(raws, availability)
    if audit_digest != receipt.get("audit_digest") or replay_digest != receipt.get("replay_digest"):
        raise EvidenceArchiveError("cold archive audit or replay digest does not match receipt")
    return raws, availability, receipt


def replay_cold_evidence(receipt_path: Path, *, allow_reconstructed: bool = False) -> Iterable[Any]:
    """Yield point-in-time ``ReplayEvent`` objects from verified cold bytes.

    The returned iterator is compatible with ``FeaturePipeline.replay_events``
    and consequently provides the minimal read path future role-bundle work
    needs after a separately authorized cold-only migration.
    """
    raws, availability, _receipt = load_cold_evidence_records(Path(receipt_path))
    return DeterministicReplay.events_from_records(raws, availability, allow_reconstructed=allow_reconstructed)


def _write_once_json(path: Path, value: Dict[str, Any], label: str) -> Dict[str, Any]:
    path = Path(path)
    try:
        _write_once(path, value)
    except EvidenceArchiveError as exc:
        raise EvidenceArchiveError("cannot write %s" % label) from exc
    return dict(value, plan_path=str(path))


def _is_protected_g1_capture_plan(capture_plan: Any) -> bool:
    """Default-deny known G1 lineage; callers may add protected bindings."""
    if not isinstance(capture_plan, dict):
        return True
    plan_id = capture_plan.get("plan_id")
    return not isinstance(plan_id, str) or "g1" in plan_id.lower()


def build_hot_retirement_plan(
    *,
    store: EventStore,
    collection_id: str,
    receipt_path: Path,
    output_path: Path,
    retirement_id: str,
    protected_capture_plans: Iterable[Dict[str, str]] = (),
) -> Dict[str, Any]:
    """Write a machine-checkable *non-executable* retirement proposal.

    The project intentionally does not implement deletion.  A later external
    authorization can replace this proposal-only boundary after selecting an
    off-host durable target and an operator-owned recovery process.  This
    function nevertheless proves every prerequisite and records an explicit
    confirmation token, making a future handoff auditable instead of relying
    on an informal shell command.
    """
    if not _IDENTIFIER.fullmatch(retirement_id):
        raise EvidenceArchiveError("retirement_id contains unsupported characters")
    receipt_path = Path(receipt_path)
    receipt = _verified_receipt(receipt_path)
    if receipt.get("collection_id") != collection_id or Path(receipt.get("source_evidence_root", "")).resolve() != store.root.resolve():
        raise EvidenceArchiveError("retirement receipt does not bind the requested hot collection")
    terminal = _collection_terminal(store, collection_id)
    capture = terminal.get("capture_plan")
    protected = {(str(item.get("plan_id", "")), str(item.get("plan_sha256", ""))) for item in protected_capture_plans if isinstance(item, dict)}
    if _is_protected_g1_capture_plan(capture) or (str(capture.get("plan_id", "")), str(capture.get("plan_sha256", ""))) in protected:
        raise EvidenceArchiveError("retirement is forbidden for active/protected G1 capture-plan evidence")
    # This includes cold bytes, record counts, terminal/audit/replay hashes and
    # plan/registry/software receipt bindings.  No plan is emitted otherwise.
    cold = verify_hot_cold_equivalence(store=store, collection_id=collection_id, receipt_path=receipt_path)
    if terminal.get("capture_plan") != receipt.get("capture_plan") or terminal.get("source_registry") != receipt.get("source_registry") or terminal.get("collector_software") != receipt.get("collector_software"):
        raise EvidenceArchiveError("terminal plan, registry or software binding differs from cold receipt")
    hot_targets = sorted({entry.get("source_path") for seal in (receipt.get("raw_seal"), receipt.get("availability_seal")) for entry in (seal or {}).get("segments", [])})
    if not hot_targets or any(not isinstance(item, str) or item.startswith("/") or ".." in Path(item).parts for item in hot_targets):
        raise EvidenceArchiveError("retirement targets are missing or escape hot evidence root")
    body = {
        "record_type": "hot_evidence_retirement_plan",
        "schema_version": RETIREMENT_PLAN_SCHEMA,
        "retirement_id": retirement_id,
        "collection_id": collection_id,
        "source_evidence_root": str(store.root.resolve()),
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": receipt["receipt_sha256"],
        "terminal_manifest_sha256": receipt["terminal_manifest_sha256"],
        "audit_digest": cold["audit_digest"],
        "replay_digest": cold["replay_digest"],
        "raw_records": cold["raw_records"],
        "availability_records": cold["availability_records"],
        "capture_plan": receipt["capture_plan"],
        "source_registry": receipt["source_registry"],
        "collector_software": receipt["collector_software"],
        "hot_targets": hot_targets,
        "retirement_execution": "DISABLED_PENDING_EXTERNAL_DURABLE_TARGET_AND_OPERATOR_AUTHORIZATION",
        "non_destructive_receipt_retained": True,
    }
    confirmation_token = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    body["confirmation_token"] = confirmation_token
    body["plan_sha256"] = _digest(body)
    return _write_once_json(Path(output_path), body, "retirement plan")


def execute_hot_retirement_plan(*, plan_path: Path, confirmation_token: str) -> None:
    """Fail closed: destructive hot-source retirement is deliberately absent.

    Keeping this explicit API prevents callers from mistaking a valid cold
    receipt or retirement plan for permission to delete local evidence.
    """
    plan = _load_json(Path(plan_path), "retirement plan")
    body = dict(plan)
    expected = body.pop("plan_sha256", None)
    if plan.get("record_type") != "hot_evidence_retirement_plan" or plan.get("schema_version") != RETIREMENT_PLAN_SCHEMA or expected != _digest(body):
        raise EvidenceArchiveError("retirement plan integrity check failed")
    if confirmation_token != plan.get("confirmation_token"):
        raise EvidenceArchiveError("retirement confirmation token does not match plan")
    raise EvidenceArchiveError("hot-source retirement execution is disabled; requires external durable-target authorization")


def verify_hot_cold_equivalence(*, store: EventStore, collection_id: str, receipt_path: Path) -> Dict[str, Any]:
    """Prove the currently sealed hot collection matches its cold sidecar."""
    receipt = _verified_receipt(Path(receipt_path))
    if receipt.get("collection_id") != collection_id or Path(receipt.get("source_evidence_root", "")).resolve() != store.root.resolve():
        raise EvidenceArchiveError("receipt does not bind the requested hot collection")
    with store._writer_lock():
        terminal, raws, availability, audit_digest, replay_digest = _validate_hot_collection(store, collection_id)
        if _sha256_file(store.collection_manifest_root / (collection_id + ".json")) != receipt.get("terminal_manifest_sha256"):
            raise EvidenceArchiveError("hot terminal manifest differs from archive receipt")
        cold = verify_evidence_archive(Path(receipt_path))
        if audit_digest != cold["audit_digest"] or replay_digest != cold["replay_digest"]:
            raise EvidenceArchiveError("hot and cold archive digests differ")
        if len(raws) != cold["raw_records"] or len(availability) != cold["availability_records"]:
            raise EvidenceArchiveError("hot and cold archive record counts differ")
        if terminal.get("audit_digest") != audit_digest:
            raise EvidenceArchiveError("hot terminal audit digest drifted")
    return dict(cold, hot_cold_equivalent=True)
