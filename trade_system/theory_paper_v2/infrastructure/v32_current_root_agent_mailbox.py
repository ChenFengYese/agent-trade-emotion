"""Write-once/CAS storage for the V3.2 current-root Codex mailbox.

This adapter owns local durability only.  It exposes no network, account,
credential, order, fill, or model invocation capability.  A caller explicitly
enqueues a complete canonical Agent context, the current root Codex explicitly
claims and submits one payload, and the controller explicitly consumes it.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path, PurePosixPath
import threading
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    atomic_replace_json,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_agent_lifecycle import (
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    build_v32_agent_consumption_v1,
    build_v32_agent_delivery_v1,
    build_v32_embedded_document_binding_v1,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_v1,
)
from ..domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID,
    SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID,
)
from ..domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD,
    CLAIM_DIGEST_FIELD,
    CLAIM_SCHEMA_ID,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    CONSUMPTION_RECEIPT_DIGEST_FIELD,
    CONSUMPTION_RECEIPT_SCHEMA_ID,
    DELIVERY_RECEIPT_DIGEST_FIELD,
    DELIVERY_RECEIPT_SCHEMA_ID,
    REQUEST_DIGEST_FIELD,
    REQUEST_SCHEMA_ID,
    STAGES,
    build_v32_current_codex_presentation_envelope_v1,
    build_v32_current_root_agent_mailbox_checkpoint_v1,
    build_v32_current_root_agent_mailbox_claim_v1,
    build_v32_current_root_agent_mailbox_consumption_receipt_v1,
    build_v32_current_root_agent_mailbox_delivery_receipt_v1,
    build_v32_current_root_agent_mailbox_request_v1,
    claim_v32_current_root_agent_mailbox_request_v1,
    consume_v32_current_root_agent_mailbox_request_v1,
    deliver_v32_current_root_agent_mailbox_request_v1,
    open_v32_current_root_agent_mailbox_request_v1,
    verify_v32_current_root_agent_mailbox_checkpoint_v1,
    verify_v32_current_root_agent_mailbox_claim_v1,
    verify_v32_current_root_agent_mailbox_consumption_receipt_v1,
    verify_v32_current_root_agent_mailbox_delivery_receipt_v1,
    verify_v32_current_root_agent_mailbox_request_v1,
    verify_v32_current_root_agent_mailbox_transition_v1,
    verify_v32_current_codex_presentation_envelope_v1,
)


class V32CurrentRootAgentMailboxStoreError(ValueError):
    """A local mailbox persistence invariant failed closed."""


STORE_ROOT = "v32-current-root-agent-mailbox-v1"
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32CurrentRootAgentMailboxStoreError("V32_MAILBOX_STORE_CYCLE_INVALID")
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CurrentRootAgentMailboxStoreError(code)
    return value


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    atomic_replace_json(
        path,
        document,
        short_write_error="V32_MAILBOX_CHECKPOINT_SHORT_WRITE",
    )


class LocalV32CurrentRootAgentMailbox:
    """Durable owner for one run's 16 independent two-stage mailboxes."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        if supplied.exists() and supplied.is_symlink():
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_ROOT_SYMLINK_FORBIDDEN"
            )
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_ROOT_INVALID"
            )
        self.run_root = supplied
        self._physical_root = supplied.resolve(strict=True)

    def _safe_path(self, relative_ref: str) -> Path:
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
        ):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_ROOT_CHANGED"
            )
        lexical = PurePosixPath(relative_ref)
        if (
            not isinstance(relative_ref, str)
            or not relative_ref
            or "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or len(lexical.parts) < 2
            or lexical.parts[0] != STORE_ROOT
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_PATH_INVALID"
            )
        current = self.run_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._physical_root)
        except V32CurrentRootAgentMailboxStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_PATH_INVALID"
            ) from exc
        return current

    @contextmanager
    def _lock(self):
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        ensure_directory_tree(lock_path.parent)
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        key = str(lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(lock_path):
                yield

    @staticmethod
    def _base(cycle_index: int) -> str:
        return f"{STORE_ROOT}/cycles/{_cycle(cycle_index):04d}"

    def _checkpoint_path(self, cycle_index: int) -> Path:
        return self._safe_path(f"{self._base(cycle_index)}/checkpoint.json")

    def _checkpoint_history_path(
        self, cycle_index: int, checkpoint_digest: str
    ) -> Path:
        return self._safe_path(
            f"{self._base(cycle_index)}/checkpoints/{checkpoint_digest}.json"
        )

    def _artifact_ref(self, cycle_index: int, stage: str, filename: str) -> str:
        if stage not in STAGES:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_STAGE_INVALID"
            )
        return f"{self._base(cycle_index)}/{stage.lower()}/{filename}"

    def _load_canonical(self, path: Path) -> Mapping[str, Any]:
        try:
            document = load_json_strict(path)
        except (OSError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_DOCUMENT_INVALID"
            ) from exc
        if path.read_bytes() != canonical_bytes(dict(document)) + b"\n":
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_NONCANONICAL_FILE"
            )
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_DOCUMENT_INVALID"
            ) from exc
        return document

    def _write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> Mapping[str, str]:
        try:
            semantic = verify_self_digest(document, digest_field)
            if document.get("schema_id") != schema_id:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_DOCUMENT_SCHEMA_INVALID"
                )
            path = self._safe_path(relative_ref)
            write_once_json(path, document)
            return build_v32_embedded_document_binding_v1(
                relative_ref=relative_ref,
                document=document,
                schema_id=schema_id,
                digest_field=digest_field,
            )
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                raise
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_WRITE_ONCE_CONFLICT"
            ) from exc

    def _read_document(
        self,
        *,
        relative_ref: str,
        schema_id: str,
        digest_field: str,
    ) -> Mapping[str, Any]:
        document = self._load_canonical(self._safe_path(relative_ref))
        try:
            verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_DOCUMENT_DIGEST_INVALID"
            ) from exc
        if document.get("schema_id") != schema_id:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_DOCUMENT_SCHEMA_INVALID"
            )
        return document

    def _binding(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> Mapping[str, str]:
        path = self._safe_path(relative_ref)
        payload = canonical_bytes(dict(document)) + b"\n"
        # Existing immutable bytes may be an orphan transition tail whose
        # parent fsync response was lost.  Re-enter the durable primitive so a
        # successful replay repairs that proof without replacing the file.
        confirm_existing_json(path, document)
        return {
            "relative_ref": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": document[digest_field],
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }

    @staticmethod
    def _same_artifact(
        left: Mapping[str, Any], right: Mapping[str, Any]
    ) -> bool:
        return all(
            left.get(field) == right.get(field)
            for field in (
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            )
        )

    def _input_material_ref(
        self, cycle_index: int, stage: str, filename: str
    ) -> str:
        return self._artifact_ref(
            cycle_index, stage, f"input-material/{filename}"
        )

    def _persist_input_materials(
        self,
        *,
        cycle_index: int,
        stage: str,
        agent_input_context: Mapping[str, Any],
        lossless_context_package: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        verify_v32_agent_input_context_v1(
            agent_input_context,
            lossless_context_package=lossless_context_package,
        )
        packet = resolve_v32_agent_canonical_packet_v1(
            agent_input_context,
            lossless_context_package=lossless_context_package,
        )
        original_binding = self._write_document(
            relative_ref=self._input_material_ref(
                cycle_index, stage, "canonical-packet-original.json"
            ),
            document=packet,
            schema_id=agent_input_context["canonical_packet_schema_id"],
            digest_field=agent_input_context["canonical_packet_digest_field"],
        )
        if not self._same_artifact(
            original_binding, agent_input_context["canonical_packet_binding"]
        ):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_ORIGINAL_BINDING_INVALID"
            )
        if agent_input_context["context_delivery_mode"] == "INLINE":
            return {
                "lossless_context_package": None,
                "ordered_delivery_units": [
                    {
                        **agent_input_context["ordered_input_delivery_units"][0],
                        "document": packet,
                    }
                ],
                "mailbox_original_binding": original_binding,
            }
        if lossless_context_package is None:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_SHARDED_PACKAGE_REQUIRED"
            )
        manifest = lossless_context_package["manifest"]
        selection = lossless_context_package["selection"]
        shards = list(lossless_context_package["shards"])
        self._write_document(
            relative_ref=self._input_material_ref(
                cycle_index, stage, "manifest.json"
            ),
            document=manifest,
            schema_id=MANIFEST_SCHEMA_ID,
            digest_field=MANIFEST_DIGEST_FIELD,
        )
        self._write_document(
            relative_ref=self._input_material_ref(
                cycle_index, stage, "selection.json"
            ),
            document=selection,
            schema_id=SELECTION_SCHEMA_ID,
            digest_field=SELECTION_DIGEST_FIELD,
        )
        for index, shard in enumerate(shards):
            self._write_document(
                relative_ref=self._input_material_ref(
                    cycle_index, stage, f"shard-{index:04d}.json"
                ),
                document=shard,
                schema_id=SHARD_SCHEMA_ID,
                digest_field=SHARD_DIGEST_FIELD,
            )
        documents = [manifest, selection, *shards]
        rows = agent_input_context["ordered_input_delivery_units"]
        if len(rows) != len(documents):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_INPUT_UNIT_SET_INVALID"
            )
        return {
            "lossless_context_package": lossless_context_package,
            "ordered_delivery_units": [
                {**row, "document": document}
                for row, document in zip(rows, documents, strict=True)
            ],
            "mailbox_original_binding": original_binding,
        }

    def _load_input_materials(
        self, *, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        context = request["agent_input_context"]
        cycle_index = request["cycle_index"]
        stage = request["stage"]
        packet = self._read_document(
            relative_ref=self._input_material_ref(
                cycle_index, stage, "canonical-packet-original.json"
            ),
            schema_id=context["canonical_packet_schema_id"],
            digest_field=context["canonical_packet_digest_field"],
        )
        if context["context_delivery_mode"] == "INLINE":
            resolve_v32_agent_canonical_packet_v1(context)
            if dict(packet) != dict(context["canonical_packet"]):
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_ORIGINAL_REPLAY_INVALID"
                )
            documents = [packet]
            package = None
        else:
            manifest = self._read_document(
                relative_ref=self._input_material_ref(
                    cycle_index, stage, "manifest.json"
                ),
                schema_id=MANIFEST_SCHEMA_ID,
                digest_field=MANIFEST_DIGEST_FIELD,
            )
            selection = self._read_document(
                relative_ref=self._input_material_ref(
                    cycle_index, stage, "selection.json"
                ),
                schema_id=SELECTION_SCHEMA_ID,
                digest_field=SELECTION_DIGEST_FIELD,
            )
            shard_count = len(context["selected_context_shard_bindings"])
            shards = [
                self._read_document(
                    relative_ref=self._input_material_ref(
                        cycle_index, stage, f"shard-{index:04d}.json"
                    ),
                    schema_id=SHARD_SCHEMA_ID,
                    digest_field=SHARD_DIGEST_FIELD,
                )
                for index in range(shard_count)
            ]
            package = {
                "manifest": manifest,
                "shards": shards,
                "original_documents": [packet],
                "selection": selection,
                "manifest_binding": context[
                    "context_compaction_manifest_binding"
                ],
                "shard_bindings": context[
                    "selected_context_shard_bindings"
                ],
                "selection_binding": context[
                    "context_shard_selection_binding"
                ],
            }
            resolve_v32_agent_canonical_packet_v1(
                context, lossless_context_package=package
            )
            documents = [manifest, selection, *shards]
        rows = context["ordered_input_delivery_units"]
        if len(rows) != len(documents):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_INPUT_UNIT_SET_INVALID"
            )
        units: list[dict[str, Any]] = []
        for row, document in zip(rows, documents, strict=True):
            physical = hashlib.sha256(
                canonical_bytes(dict(document)) + b"\n"
            ).hexdigest()
            logical = row["artifact_binding"]
            if (
                document.get("schema_id") != logical.get("schema_id")
                or document.get(logical.get("digest_field"))
                != logical.get("semantic_digest")
                or physical != logical.get("physical_sha256")
            ):
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_INPUT_UNIT_BINDING_INVALID"
                )
            units.append({**row, "document": document})
        return {
            "canonical_packet_original": packet,
            "lossless_context_package": package,
            "ordered_delivery_units": units,
        }

    def initialize_checkpoint(
        self,
        *,
        mailbox_id: str,
        run_id: str,
        cycle_index: int,
        created_at: str,
    ) -> Mapping[str, Any]:
        candidate = build_v32_current_root_agent_mailbox_checkpoint_v1(
            mailbox_id=mailbox_id,
            run_id=run_id,
            cycle_index=cycle_index,
            created_at=created_at,
        )
        with self._lock():
            current_path = self._checkpoint_path(cycle_index)
            if current_path.exists():
                current = self.load_checkpoint(
                    run_id=run_id, cycle_index=cycle_index, _already_locked=True
                )
                if current != candidate:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_ALREADY_INITIALIZED"
                    )
                digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
                    current
                )
                confirm_existing_json(
                    self._checkpoint_history_path(cycle_index, digest), current
                )
                confirm_existing_json(current_path, current)
                return current
            digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(candidate)
            write_once_json(
                self._checkpoint_history_path(cycle_index, digest), candidate
            )
            _atomic_json(current_path, candidate)
            return candidate

    def checkpoint_exists(self, *, cycle_index: int) -> bool:
        """Report only physical presence; callers must still fully load to trust it."""

        with self._lock():
            return self._checkpoint_path(cycle_index).is_file()

    def load_checkpoint(
        self,
        *,
        run_id: str,
        cycle_index: int,
        _already_locked: bool = False,
    ) -> Mapping[str, Any]:
        def load() -> Mapping[str, Any]:
            document = self._load_canonical(self._checkpoint_path(cycle_index))
            try:
                digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(document)
            except (TypeError, ValueError) as exc:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CHECKPOINT_INVALID"
                ) from exc
            if document.get("run_id") != run_id:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_RUN_MISMATCH"
                )
            history = self._checkpoint_history_path(cycle_index, digest)
            if not history.is_file() or history.read_bytes() != canonical_bytes(
                dict(document)
            ) + b"\n":
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CHECKPOINT_HISTORY_INVALID"
                )
            try:
                confirm_existing_json(history, document)
            except (OSError, TypeError, ValueError) as exc:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CHECKPOINT_HISTORY_INVALID"
                ) from exc
            return document

        if _already_locked:
            return load()
        with self._lock():
            return load()

    def json_prefix_inventory_v1(
        self, *, run_id: str, cycle_index: int
    ) -> list[Mapping[str, str]]:
        """Bind every extant self-digested JSON in one mailbox cycle prefix."""

        with self._lock():
            if self._checkpoint_path(cycle_index).is_file():
                self.load_checkpoint(
                    run_id=run_id,
                    cycle_index=cycle_index,
                    _already_locked=True,
                )
            base = self._safe_path(self._base(cycle_index))
            if not base.exists():
                return []
            rows: list[Mapping[str, str]] = []
            for path in sorted(base.rglob("*.json")):
                if path.is_symlink() or not path.is_file():
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_PREFIX_INVENTORY_INVALID"
                    )
                relative_ref = path.relative_to(self.run_root).as_posix()
                document = self._load_canonical(path)
                fields: list[str] = []
                for key, value in document.items():
                    if not (
                        isinstance(key, str)
                        and key.endswith("_digest")
                        and isinstance(value, str)
                        and len(value) == 64
                    ):
                        continue
                    try:
                        verify_self_digest(document, key)
                    except (TypeError, ValueError):
                        continue
                    fields.append(key)
                if (
                    len(fields) != 1
                    or not isinstance(document.get("schema_id"), str)
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_PREFIX_INVENTORY_INVALID"
                    )
                rows.append(
                    self._binding(
                        relative_ref=relative_ref,
                        document=document,
                        schema_id=str(document["schema_id"]),
                        digest_field=fields[0],
                    )
                )
            return rows

    def _current(
        self, *, run_id: str, cycle_index: int, expected_checkpoint_digest: str
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(
            run_id=run_id, cycle_index=cycle_index, _already_locked=True
        )
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            )
        return current

    def _current_or_committed_successor(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
        """Load the requested CAS base or its one already-committed successor.

        Every mailbox mutation is single-attempt and the expected checkpoint
        digest is its idempotency key.  If the process lost its response after
        the checkpoint pointer advanced, the caller is allowed to replay only
        that exact one-step transition.  Anything older/newer remains a hard
        CAS conflict.
        """

        current = self.load_checkpoint(
            run_id=run_id,
            cycle_index=cycle_index,
            _already_locked=True,
        )
        if current[CHECKPOINT_DIGEST_FIELD] == expected_checkpoint_digest:
            return current, None
        history_path = self._checkpoint_history_path(
            cycle_index, expected_checkpoint_digest
        )
        if not history_path.is_file():
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            )
        before = self._load_canonical(history_path)
        try:
            before_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
                before
            )
            verify_v32_current_root_agent_mailbox_transition_v1(before, current)
        except (TypeError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            ) from exc
        if (
            before_digest != expected_checkpoint_digest
            or before.get("run_id") != run_id
            or before.get("cycle_index") != cycle_index
            or current.get("predecessor_checkpoint_digest")
            != expected_checkpoint_digest
        ):
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            )
        return before, current

    def _commit(
        self,
        *,
        current: Mapping[str, Any],
        after: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            )
        try:
            digest = verify_v32_current_root_agent_mailbox_transition_v1(
                current, after
            )
        except (TypeError, ValueError) as exc:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_TRANSITION_INVALID"
            ) from exc
        write_once_json(
            self._checkpoint_history_path(after["cycle_index"], digest), after
        )
        latest = self._load_canonical(self._checkpoint_path(after["cycle_index"]))
        if latest.get(CHECKPOINT_DIGEST_FIELD) != expected_checkpoint_digest:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_CAS_CONFLICT"
            )
        _atomic_json(self._checkpoint_path(after["cycle_index"]), after)
        return after

    def _stage_documents(
        self,
        *,
        cycle_index: int,
        stage: str,
        allow_partial_transition_tail: bool = False,
    ) -> dict[str, Mapping[str, Any] | None]:
        request = self._read_document(
            relative_ref=self._artifact_ref(cycle_index, stage, "request.json"),
            schema_id=REQUEST_SCHEMA_ID,
            digest_field=REQUEST_DIGEST_FIELD,
        )
        verify_v32_current_root_agent_mailbox_request_v1(request)
        input_materials = self._load_input_materials(request=request)
        result: dict[str, Mapping[str, Any] | None] = {
            "request": request,
            "input_materials": input_materials,
            "claim": None,
            "agent_delivery": None,
            "delivery_receipt": None,
            "agent_consumption": None,
            "consumption_receipt": None,
        }
        optional = (
            ("claim", "claim.json", CLAIM_SCHEMA_ID, CLAIM_DIGEST_FIELD),
            (
                "agent_delivery",
                "agent-delivery.json",
                AGENT_DELIVERY_SCHEMA_ID,
                AGENT_DELIVERY_DIGEST_FIELD,
            ),
            (
                "delivery_receipt",
                "delivery-receipt.json",
                DELIVERY_RECEIPT_SCHEMA_ID,
                DELIVERY_RECEIPT_DIGEST_FIELD,
            ),
            (
                "agent_consumption",
                "agent-consumption.json",
                AGENT_CONSUMPTION_SCHEMA_ID,
                AGENT_CONSUMPTION_DIGEST_FIELD,
            ),
            (
                "consumption_receipt",
                "consumption-receipt.json",
                CONSUMPTION_RECEIPT_SCHEMA_ID,
                CONSUMPTION_RECEIPT_DIGEST_FIELD,
            ),
        )
        for key, filename, schema_id, digest_field in optional:
            ref = self._artifact_ref(cycle_index, stage, filename)
            if self._safe_path(ref).exists():
                result[key] = self._read_document(
                    relative_ref=ref,
                    schema_id=schema_id,
                    digest_field=digest_field,
                )
        claim = result["claim"]
        delivery = result["agent_delivery"]
        delivery_receipt = result["delivery_receipt"]
        consumption = result["agent_consumption"]
        consumption_receipt = result["consumption_receipt"]
        try:
            if claim is not None:
                verify_v32_current_root_agent_mailbox_claim_v1(
                    claim, request=request
                )
            if delivery is not None or delivery_receipt is not None:
                if claim is None or delivery is None:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE"
                    )
                verify_v32_agent_delivery_v1(
                    delivery, agent_input_context=request["agent_input_context"]
                )
                if delivery_receipt is None:
                    if not allow_partial_transition_tail:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE"
                        )
                else:
                    verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
                        delivery_receipt,
                        request=request,
                        claim=claim,
                        agent_delivery=delivery,
                    )
            if consumption is not None or consumption_receipt is not None:
                if (
                    claim is None
                    or delivery is None
                    or delivery_receipt is None
                    or consumption is None
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE"
                    )
                verify_v32_agent_consumption_v1(
                    consumption,
                    agent_input_context=request["agent_input_context"],
                    agent_delivery=delivery,
                )
                if consumption_receipt is None:
                    if not allow_partial_transition_tail:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE"
                        )
                else:
                    verify_v32_current_root_agent_mailbox_consumption_receipt_v1(
                        consumption_receipt,
                        request=request,
                        claim=claim,
                        delivery_receipt=delivery_receipt,
                        agent_delivery=delivery,
                        agent_consumption=consumption,
                    )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                raise
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_STAGE_CHAIN_INVALID"
            ) from exc
        return result

    def enqueue_request(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
        agent_input_context: Mapping[str, Any],
        agent_input_context_binding: Mapping[str, Any],
        reserved_at: str,
        lossless_context_package: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        with self._lock():
            current, committed = self._current_or_committed_successor(
                run_id=run_id,
                cycle_index=cycle_index,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )
            try:
                stage_hint = agent_input_context.get("agent_stage")
                if agent_input_context.get("context_delivery_mode") != "INLINE":
                    # The present local Codex pilot has one bounded, atomic
                    # Agent-facing object.  LOSSLESS_SHARDED remains a domain
                    # construction primitive, not a qualified production
                    # transport; pretending otherwise would exceed 1 MiB.
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_INLINE_ONLY"
                    )
                if committed is not None:
                    if stage_hint not in STAGES:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_ENQUEUE_REPLAY_INVALID"
                        )
                    if (
                        current["stage_states"][str(stage_hint)]["status"]
                        != "READY"
                        or committed["stage_states"][str(stage_hint)]["status"]
                        != "REQUESTED"
                    ):
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_CAS_CONFLICT"
                        )
                    existing = self._stage_documents(
                        cycle_index=cycle_index, stage=str(stage_hint)
                    )
                    request = existing["request"]
                    material = existing["input_materials"]
                    if (
                        request is None
                        or existing["claim"] is not None
                        or existing["agent_delivery"] is not None
                        or existing["delivery_receipt"] is not None
                        or existing["agent_consumption"] is not None
                        or existing["consumption_receipt"] is not None
                        or request.get("agent_input_context")
                        != agent_input_context
                        or request.get("agent_input_context_binding")
                        != agent_input_context_binding
                        or material["lossless_context_package"]
                        != lossless_context_package
                    ):
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_ENQUEUE_REPLAY_INVALID"
                        )
                    replay_after = open_v32_current_root_agent_mailbox_request_v1(
                        checkpoint=current, request=request
                    )
                    if replay_after != committed:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_ENQUEUE_REPLAY_INVALID"
                        )
                    request_ref = self._artifact_ref(
                        cycle_index, str(stage_hint), "request.json"
                    )
                    return {
                        "checkpoint": committed,
                        "request": request,
                        "request_binding": self._binding(
                            relative_ref=request_ref,
                            document=request,
                            schema_id=REQUEST_SCHEMA_ID,
                            digest_field=REQUEST_DIGEST_FIELD,
                        ),
                        "ordered_agent_input_delivery_units": material[
                            "ordered_delivery_units"
                        ],
                    }
                if stage_hint in STAGES:
                    request_ref = self._artifact_ref(
                        cycle_index, str(stage_hint), "request.json"
                    )
                    if self._safe_path(request_ref).is_file():
                        # A prior process may have durably published the exact
                        # request/material tail and then failed before the
                        # checkpoint CAS.  The first immutable bytes win;
                        # finish only that deterministic transition instead
                        # of rebuilding it with a new reservation timestamp.
                        existing = self._stage_documents(
                            cycle_index=cycle_index, stage=str(stage_hint)
                        )
                        request = existing["request"]
                        material = existing["input_materials"]
                        if (
                            request is None
                            or existing["claim"] is not None
                            or existing["agent_delivery"] is not None
                            or existing["delivery_receipt"] is not None
                            or existing["agent_consumption"] is not None
                            or existing["consumption_receipt"] is not None
                            or request.get("agent_input_context")
                            != agent_input_context
                            or request.get("agent_input_context_binding")
                            != agent_input_context_binding
                            or material["lossless_context_package"]
                            != lossless_context_package
                        ):
                            raise V32CurrentRootAgentMailboxStoreError(
                                "V32_MAILBOX_STORE_ENQUEUE_ORPHAN_CONFLICT"
                            )
                        after = open_v32_current_root_agent_mailbox_request_v1(
                            checkpoint=current, request=request
                        )
                        capacity_claimed_at = (
                            "9999-12-31T23:59:59.999998Z"
                        )
                        capacity_claim = (
                            build_v32_current_root_agent_mailbox_claim_v1(
                                request=request,
                                claimed_at=capacity_claimed_at,
                            )
                        )
                        capacity_checkpoint = (
                            claim_v32_current_root_agent_mailbox_request_v1(
                                checkpoint=after,
                                request=request,
                                claim=capacity_claim,
                            )
                        )
                        build_v32_current_codex_presentation_envelope_v1(
                            mailbox_checkpoint=capacity_checkpoint,
                            request=request,
                            claim=capacity_claim,
                            lossless_context_package=material[
                                "lossless_context_package"
                            ],
                            control_context={
                                "presentation_kind": "TARGET_AGENT_CLAIM",
                                "stage": stage_hint,
                                "stage_status": "CLAIMED",
                                "next_action": (
                                    "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
                                ),
                                "active_analysis_permit_digest": "0" * 64,
                                "supervisor_checkpoint_digest": "0" * 64,
                                "permit_deadline_at": (
                                    "9999-12-31T23:59:59.999999Z"
                                ),
                                "agent_boundary_at": capacity_claimed_at,
                            },
                        )
                        request_binding = self._binding(
                            relative_ref=request_ref,
                            document=request,
                            schema_id=REQUEST_SCHEMA_ID,
                            digest_field=REQUEST_DIGEST_FIELD,
                        )
                        checkpoint = self._commit(
                            current=current,
                            after=after,
                            expected_checkpoint_digest=(
                                expected_checkpoint_digest
                            ),
                        )
                        return {
                            "checkpoint": checkpoint,
                            "request": request,
                            "request_binding": request_binding,
                            "ordered_agent_input_delivery_units": material[
                                "ordered_delivery_units"
                            ],
                        }
                request = build_v32_current_root_agent_mailbox_request_v1(
                    mailbox_id=current["mailbox_id"],
                    agent_input_context=agent_input_context,
                    agent_input_context_binding=agent_input_context_binding,
                    reserved_at=reserved_at,
                )
                stage = request["stage"]
                if stage == "SELECTION":
                    proposal = self._stage_documents(
                        cycle_index=cycle_index, stage="PROPOSAL"
                    )
                    packet = resolve_v32_agent_canonical_packet_v1(
                        request["agent_input_context"],
                        lossless_context_package=lossless_context_package,
                    )
                    if (
                        proposal["claim"] is None
                        or proposal["agent_delivery"] is None
                        or proposal["delivery_receipt"] is None
                        or proposal["agent_consumption"] is None
                        or proposal["consumption_receipt"] is None
                        or current["stage_states"]["PROPOSAL"][
                            "consumption_receipt_digest"
                        ]
                        != proposal["consumption_receipt"][
                            CONSUMPTION_RECEIPT_DIGEST_FIELD
                        ]
                        or packet.get("proposal_input_context")
                        != proposal["request"]["agent_input_context"]
                        or packet.get("proposal_input_context_binding")
                        != proposal["request"]["agent_input_context_binding"]
                        or packet.get("proposal_delivery")
                        != proposal["agent_delivery"]
                        or packet.get("proposal_delivery_binding")
                        != proposal["delivery_receipt"][
                            "agent_delivery_binding"
                        ]
                        or packet.get("proposal_consumption")
                        != proposal["agent_consumption"]
                        or packet.get("proposal_consumption_binding")
                        != proposal["consumption_receipt"][
                            "agent_consumption_binding"
                        ]
                    ):
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_SELECTION_PROPOSAL_CHAIN_INVALID"
                        )
                after = open_v32_current_root_agent_mailbox_request_v1(
                    checkpoint=current, request=request
                )
                capacity_claimed_at = "9999-12-31T23:59:59.999998Z"
                capacity_claim = build_v32_current_root_agent_mailbox_claim_v1(
                    request=request, claimed_at=capacity_claimed_at
                )
                capacity_checkpoint = claim_v32_current_root_agent_mailbox_request_v1(
                    checkpoint=after,
                    request=request,
                    claim=capacity_claim,
                )
                build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=capacity_checkpoint,
                    request=request,
                    claim=capacity_claim,
                    lossless_context_package=lossless_context_package,
                    control_context={
                        "presentation_kind": "TARGET_AGENT_CLAIM",
                        "stage": stage,
                        "stage_status": "CLAIMED",
                        "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                        "active_analysis_permit_digest": "0" * 64,
                        "supervisor_checkpoint_digest": "0" * 64,
                        "permit_deadline_at": "9999-12-31T23:59:59.999999Z",
                        "agent_boundary_at": capacity_claimed_at,
                    },
                )
                material = self._persist_input_materials(
                    cycle_index=cycle_index,
                    stage=stage,
                    agent_input_context=agent_input_context,
                    lossless_context_package=lossless_context_package,
                )
                request_ref = self._artifact_ref(
                    cycle_index, stage, "request.json"
                )
                request_binding = self._write_document(
                    relative_ref=request_ref,
                    document=request,
                    schema_id=REQUEST_SCHEMA_ID,
                    digest_field=REQUEST_DIGEST_FIELD,
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                    raise
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_ENQUEUE_INVALID"
                ) from exc
            checkpoint = self._commit(
                current=current,
                after=after,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )
            return {
                "checkpoint": checkpoint,
                "request": request,
                "request_binding": request_binding,
                "ordered_agent_input_delivery_units": material[
                    "ordered_delivery_units"
                ],
            }

    def claim_request(
        self,
        *,
        run_id: str,
        cycle_index: int,
        stage: str,
        expected_checkpoint_digest: str,
        claimed_at: str,
    ) -> Mapping[str, Any]:
        with self._lock():
            current, committed = self._current_or_committed_successor(
                run_id=run_id,
                cycle_index=cycle_index,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )
            documents = self._stage_documents(cycle_index=cycle_index, stage=stage)
            request = documents["request"]
            assert request is not None
            try:
                if committed is not None and (
                    current["stage_states"][stage]["status"] != "REQUESTED"
                    or committed["stage_states"][stage]["status"] != "CLAIMED"
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CAS_CONFLICT"
                    )
                if any(
                    documents[name] is not None
                    for name in (
                        "agent_delivery",
                        "delivery_receipt",
                        "agent_consumption",
                        "consumption_receipt",
                    )
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CLAIM_TAIL_CONFLICT"
                    )
                existing_claim = documents["claim"]
                if existing_claim is None:
                    claim = build_v32_current_root_agent_mailbox_claim_v1(
                        request=request, claimed_at=claimed_at
                    )
                    claim_binding = self._write_document(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "claim.json"
                        ),
                        document=claim,
                        schema_id=CLAIM_SCHEMA_ID,
                        digest_field=CLAIM_DIGEST_FIELD,
                    )
                else:
                    # Recover the first immutable claim after a crash between
                    # artifact publication and checkpoint advancement.  A new
                    # wall-clock value must never create attempt two.
                    claim = existing_claim
                    claim_binding = self._binding(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "claim.json"
                        ),
                        document=claim,
                        schema_id=CLAIM_SCHEMA_ID,
                        digest_field=CLAIM_DIGEST_FIELD,
                    )
                after = claim_v32_current_root_agent_mailbox_request_v1(
                    checkpoint=current, request=request, claim=claim
                )
                build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=after,
                    request=request,
                    claim=claim,
                    lossless_context_package=documents["input_materials"][
                        "lossless_context_package"
                    ],
                    control_context={
                        "presentation_kind": "MAILBOX_AGENT_CLAIM",
                        "stage": stage,
                        "stage_status": "CLAIMED",
                        "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                    },
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                    raise
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CLAIM_INVALID"
                ) from exc
            if committed is not None:
                if after != committed:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CLAIM_REPLAY_INVALID"
                    )
                checkpoint = committed
            else:
                checkpoint = self._commit(
                    current=current,
                    after=after,
                    expected_checkpoint_digest=expected_checkpoint_digest,
                )
            return {
                "checkpoint": checkpoint,
                "request": request,
                "claim": claim,
                "claim_binding": claim_binding,
            }

    def submit_delivery(
        self,
        *,
        run_id: str,
        cycle_index: int,
        stage: str,
        expected_checkpoint_digest: str,
        current_codex_presentation_envelope: Mapping[str, Any],
        expected_current_codex_presentation_digest: str,
        delivered_at: str,
        payload_utf8: str,
    ) -> Mapping[str, Any]:
        """Persist one explicit current-root payload; never generate one."""

        with self._lock():
            current, committed = self._current_or_committed_successor(
                run_id=run_id,
                cycle_index=cycle_index,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )
            documents = self._stage_documents(
                cycle_index=cycle_index,
                stage=stage,
                allow_partial_transition_tail=True,
            )
            request = documents["request"]
            claim = documents["claim"]
            if request is None or claim is None:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_DELIVERY_REQUIRES_CLAIM"
                )
            try:
                if committed is not None and (
                    current["stage_states"][stage]["status"] != "CLAIMED"
                    or committed["stage_states"][stage]["status"]
                    != "DELIVERED"
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CAS_CONFLICT"
                    )
                presentation_digest = (
                    verify_v32_current_codex_presentation_envelope_v1(
                        current_codex_presentation_envelope
                    )
                )
                if (
                    presentation_digest
                    != expected_current_codex_presentation_digest
                    or current_codex_presentation_envelope.get(
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    )
                    != expected_current_codex_presentation_digest
                    or current_codex_presentation_envelope.get(
                        "mailbox_checkpoint"
                    )
                    != current
                    or current_codex_presentation_envelope.get("request")
                    != request
                    or current_codex_presentation_envelope.get("claim")
                    != claim
                    or current_codex_presentation_envelope.get(
                        "lossless_context_package"
                    )
                    != documents["input_materials"][
                        "lossless_context_package"
                    ]
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_PRESENTATION_BINDING_INVALID"
                    )
                verify_v32_current_root_agent_mailbox_claim_v1(
                    claim, request=request
                )
                if (
                    documents["agent_consumption"] is not None
                    or documents["consumption_receipt"] is not None
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_DELIVERY_TAIL_CONFLICT"
                    )
                delivery_ref = self._artifact_ref(
                    cycle_index, stage, "agent-delivery.json"
                )
                existing_delivery = documents["agent_delivery"]
                if existing_delivery is None:
                    agent_delivery = build_v32_agent_delivery_v1(
                        agent_input_context=request["agent_input_context"],
                        agent_input_context_binding=request[
                            "agent_input_context_binding"
                        ],
                        reserved_at=claim["claimed_at"],
                        delivered_at=delivered_at,
                        payload_utf8=payload_utf8,
                    )
                    delivery_binding = build_v32_embedded_document_binding_v1(
                        relative_ref=delivery_ref,
                        document=agent_delivery,
                        schema_id=AGENT_DELIVERY_SCHEMA_ID,
                        digest_field=AGENT_DELIVERY_DIGEST_FIELD,
                    )
                    persisted_delivery_binding = self._write_document(
                        relative_ref=delivery_ref,
                        document=agent_delivery,
                        schema_id=AGENT_DELIVERY_SCHEMA_ID,
                        digest_field=AGENT_DELIVERY_DIGEST_FIELD,
                    )
                    if persisted_delivery_binding != delivery_binding:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_DELIVERY_BINDING_DRIFT"
                        )
                else:
                    # The first durable payload/time pair is the transition
                    # intent.  Retrying with different arguments can only
                    # finish or replay it, never overwrite it.
                    agent_delivery = existing_delivery
                    delivery_binding = self._binding(
                        relative_ref=delivery_ref,
                        document=agent_delivery,
                        schema_id=AGENT_DELIVERY_SCHEMA_ID,
                        digest_field=AGENT_DELIVERY_DIGEST_FIELD,
                    )
                existing_receipt = documents["delivery_receipt"]
                if existing_receipt is None:
                    receipt = (
                        build_v32_current_root_agent_mailbox_delivery_receipt_v1(
                            request=request,
                            claim=claim,
                            current_codex_presentation_digest=(
                                presentation_digest
                            ),
                            agent_delivery=agent_delivery,
                            agent_delivery_binding=delivery_binding,
                        )
                    )
                    receipt_binding = self._write_document(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "delivery-receipt.json"
                        ),
                        document=receipt,
                        schema_id=DELIVERY_RECEIPT_SCHEMA_ID,
                        digest_field=DELIVERY_RECEIPT_DIGEST_FIELD,
                    )
                else:
                    receipt = existing_receipt
                    verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
                        receipt,
                        request=request,
                        claim=claim,
                        agent_delivery=agent_delivery,
                    )
                    if receipt.get(
                        "current_codex_presentation_digest"
                    ) != presentation_digest:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_PRESENTATION_BINDING_INVALID"
                        )
                    receipt_binding = self._binding(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "delivery-receipt.json"
                        ),
                        document=receipt,
                        schema_id=DELIVERY_RECEIPT_SCHEMA_ID,
                        digest_field=DELIVERY_RECEIPT_DIGEST_FIELD,
                    )
                after = deliver_v32_current_root_agent_mailbox_request_v1(
                    checkpoint=current,
                    request=request,
                    claim=claim,
                    delivery_receipt=receipt,
                    agent_delivery=agent_delivery,
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                    raise
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_DELIVERY_INVALID"
                ) from exc
            if committed is not None:
                if after != committed:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_DELIVERY_REPLAY_INVALID"
                    )
                checkpoint = committed
            else:
                checkpoint = self._commit(
                    current=current,
                    after=after,
                    expected_checkpoint_digest=expected_checkpoint_digest,
                )
            return {
                "checkpoint": checkpoint,
                "request": request,
                "claim": claim,
                "agent_delivery": agent_delivery,
                "agent_delivery_binding": delivery_binding,
                "delivery_receipt": receipt,
                "delivery_receipt_binding": receipt_binding,
            }

    def consume_delivery(
        self,
        *,
        run_id: str,
        cycle_index: int,
        stage: str,
        expected_checkpoint_digest: str,
        consumed_at: str,
    ) -> Mapping[str, Any]:
        with self._lock():
            current, committed = self._current_or_committed_successor(
                run_id=run_id,
                cycle_index=cycle_index,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )
            documents = self._stage_documents(
                cycle_index=cycle_index,
                stage=stage,
                allow_partial_transition_tail=True,
            )
            request = documents["request"]
            claim = documents["claim"]
            agent_delivery = documents["agent_delivery"]
            delivery_receipt = documents["delivery_receipt"]
            if any(
                value is None
                for value in (request, claim, agent_delivery, delivery_receipt)
            ):
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CONSUMPTION_REQUIRES_DELIVERY"
                )
            assert request is not None
            assert claim is not None
            assert agent_delivery is not None
            assert delivery_receipt is not None
            try:
                if committed is not None and (
                    current["stage_states"][stage]["status"] != "DELIVERED"
                    or committed["stage_states"][stage]["status"]
                    != "CONSUMED"
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CAS_CONFLICT"
                    )
                verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
                    delivery_receipt,
                    request=request,
                    claim=claim,
                    agent_delivery=agent_delivery,
                )
                agent_delivery_binding = delivery_receipt[
                    "agent_delivery_binding"
                ]
                consumption_ref = self._artifact_ref(
                    cycle_index, stage, "agent-consumption.json"
                )
                existing_consumption = documents["agent_consumption"]
                if existing_consumption is None:
                    agent_consumption = build_v32_agent_consumption_v1(
                        agent_input_context=request["agent_input_context"],
                        agent_input_context_binding=request[
                            "agent_input_context_binding"
                        ],
                        agent_delivery=agent_delivery,
                        agent_delivery_binding=agent_delivery_binding,
                        consumed_at=consumed_at,
                    )
                    consumption_binding = (
                        build_v32_embedded_document_binding_v1(
                            relative_ref=consumption_ref,
                            document=agent_consumption,
                            schema_id=AGENT_CONSUMPTION_SCHEMA_ID,
                            digest_field=AGENT_CONSUMPTION_DIGEST_FIELD,
                        )
                    )
                    persisted_consumption_binding = self._write_document(
                        relative_ref=consumption_ref,
                        document=agent_consumption,
                        schema_id=AGENT_CONSUMPTION_SCHEMA_ID,
                        digest_field=AGENT_CONSUMPTION_DIGEST_FIELD,
                    )
                    if persisted_consumption_binding != consumption_binding:
                        raise V32CurrentRootAgentMailboxStoreError(
                            "V32_MAILBOX_STORE_CONSUMPTION_BINDING_DRIFT"
                        )
                else:
                    agent_consumption = existing_consumption
                    consumption_binding = self._binding(
                        relative_ref=consumption_ref,
                        document=agent_consumption,
                        schema_id=AGENT_CONSUMPTION_SCHEMA_ID,
                        digest_field=AGENT_CONSUMPTION_DIGEST_FIELD,
                    )
                existing_receipt = documents["consumption_receipt"]
                if existing_receipt is None:
                    receipt = (
                        build_v32_current_root_agent_mailbox_consumption_receipt_v1(
                            request=request,
                            claim=claim,
                            delivery_receipt=delivery_receipt,
                            agent_delivery=agent_delivery,
                            agent_consumption=agent_consumption,
                            agent_consumption_binding=consumption_binding,
                        )
                    )
                    receipt_binding = self._write_document(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "consumption-receipt.json"
                        ),
                        document=receipt,
                        schema_id=CONSUMPTION_RECEIPT_SCHEMA_ID,
                        digest_field=CONSUMPTION_RECEIPT_DIGEST_FIELD,
                    )
                else:
                    receipt = existing_receipt
                    verify_v32_current_root_agent_mailbox_consumption_receipt_v1(
                        receipt,
                        request=request,
                        claim=claim,
                        delivery_receipt=delivery_receipt,
                        agent_delivery=agent_delivery,
                        agent_consumption=agent_consumption,
                    )
                    receipt_binding = self._binding(
                        relative_ref=self._artifact_ref(
                            cycle_index, stage, "consumption-receipt.json"
                        ),
                        document=receipt,
                        schema_id=CONSUMPTION_RECEIPT_SCHEMA_ID,
                        digest_field=CONSUMPTION_RECEIPT_DIGEST_FIELD,
                    )
                after = consume_v32_current_root_agent_mailbox_request_v1(
                    checkpoint=current,
                    request=request,
                    claim=claim,
                    delivery_receipt=delivery_receipt,
                    agent_delivery=agent_delivery,
                    consumption_receipt=receipt,
                    agent_consumption=agent_consumption,
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, V32CurrentRootAgentMailboxStoreError):
                    raise
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CONSUMPTION_INVALID"
                ) from exc
            if committed is not None:
                if after != committed:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CONSUMPTION_REPLAY_INVALID"
                    )
                checkpoint = committed
            else:
                checkpoint = self._commit(
                    current=current,
                    after=after,
                    expected_checkpoint_digest=expected_checkpoint_digest,
                )
            return {
                "checkpoint": checkpoint,
                "request": request,
                "claim": claim,
                "agent_delivery": agent_delivery,
                "agent_delivery_binding": agent_delivery_binding,
                "delivery_receipt": delivery_receipt,
                "agent_consumption": agent_consumption,
                "agent_consumption_binding": consumption_binding,
                "consumption_receipt": receipt,
                "consumption_receipt_binding": receipt_binding,
                "canonical_packet_original": documents["input_materials"][
                    "canonical_packet_original"
                ],
                "lossless_context_package": documents["input_materials"][
                    "lossless_context_package"
                ],
            }

    def next_pending_request(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any] | None:
        """Read the one current-root request without claiming or advancing it."""

        with self._lock():
            checkpoint = self.load_checkpoint(
                run_id=run_id, cycle_index=cycle_index, _already_locked=True
            )
            active = checkpoint["active_stage"]
            if active not in STAGES:
                return None
            state = checkpoint["stage_states"][active]["status"]
            documents = self._stage_documents(
                cycle_index=cycle_index, stage=active
            )
            action = {
                "REQUESTED": "CURRENT_ROOT_CODEX_CLAIM",
                "CLAIMED": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                "DELIVERED": "CONTROLLER_CONSUME_DELIVERY",
            }.get(state)
            if action is None:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_PENDING_STATE_INVALID"
                )
            return {
                "run_id": run_id,
                "cycle_index": cycle_index,
                "stage": active,
                "stage_status": state,
                "next_action": action,
                "checkpoint_digest": checkpoint[CHECKPOINT_DIGEST_FIELD],
                "request": documents["request"],
                "claim": documents["claim"],
                "ordered_agent_input_delivery_units": documents[
                    "input_materials"
                ]["ordered_delivery_units"],
                "canonical_packet_original_binding": documents["request"][
                    "agent_input_context"
                ]["canonical_packet_binding"],
                "network_request_count": 0,
                "account_access": False,
                "order_submission": False,
                "retry_allowed": False,
                "executable": False,
            }

    def load_stage_chain(
        self, *, run_id: str, cycle_index: int, stage: str
    ) -> Mapping[str, Any]:
        """Read and fully replay one durable stage without changing state."""

        if stage not in STAGES:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_STAGE_INVALID"
            )
        with self._lock():
            checkpoint = self.load_checkpoint(
                run_id=run_id,
                cycle_index=cycle_index,
                _already_locked=True,
            )
            documents = self._stage_documents(
                cycle_index=cycle_index, stage=stage
            )
            state = checkpoint["stage_states"][stage]
            if state["status"] == "CONSUMED" and any(
                documents[name] is None
                for name in (
                    "claim",
                    "agent_delivery",
                    "delivery_receipt",
                    "agent_consumption",
                    "consumption_receipt",
                )
            ):
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_STAGE_CHAIN_INCOMPLETE"
                )
            materials = documents["input_materials"]
            return {
                "run_id": run_id,
                "cycle_index": cycle_index,
                "stage": stage,
                "stage_status": state["status"],
                "checkpoint_digest": checkpoint[CHECKPOINT_DIGEST_FIELD],
                "request": documents["request"],
                "claim": documents["claim"],
                "agent_delivery": documents["agent_delivery"],
                "delivery_receipt": documents["delivery_receipt"],
                "agent_consumption": documents["agent_consumption"],
                "consumption_receipt": documents["consumption_receipt"],
                "canonical_packet_original": materials[
                    "canonical_packet_original"
                ],
                "lossless_context_package": materials[
                    "lossless_context_package"
                ],
                "ordered_agent_input_delivery_units": materials[
                    "ordered_delivery_units"
                ],
                "read_only": True,
                "network_request_count": 0,
                "account_access": False,
                "order_submission": False,
                "executable": False,
            }

    def load_verified_recovery_stage_view(
        self, *, run_id: str, cycle_index: int, stage: str
    ) -> Mapping[str, Any]:
        """Reopen one stage including an exact immutable pre-CAS tail.

        Normal readers deliberately require a complete artifact chain.  A
        mutation owner has one narrower need after process/response loss: it
        must be able to see the already-published first delivery or
        consumption and finish only its missing receipt/checkpoint CAS.  This
        view is assembled and verified under the mailbox lock; it never
        creates a timestamp, payload, Agent attempt, receipt, or checkpoint.
        """

        if stage not in STAGES:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_STAGE_INVALID"
            )
        with self._lock():
            checkpoint = self.load_checkpoint(
                run_id=run_id,
                cycle_index=cycle_index,
                _already_locked=True,
            )
            documents = self._stage_documents(
                cycle_index=cycle_index,
                stage=stage,
                allow_partial_transition_tail=True,
            )
            request = documents["request"]
            claim = documents["claim"]
            delivery = documents["agent_delivery"]
            delivery_receipt = documents["delivery_receipt"]
            consumption = documents["agent_consumption"]
            consumption_receipt = documents["consumption_receipt"]
            state = checkpoint["stage_states"][stage]
            status = state["status"]
            present = (
                claim is not None,
                delivery is not None,
                delivery_receipt is not None,
                consumption is not None,
                consumption_receipt is not None,
            )
            allowed: dict[str, dict[tuple[bool, ...], str | None]] = {
                "REQUESTED": {
                    (False, False, False, False, False): None,
                    (True, False, False, False, False): "CLAIM_ONLY_PRE_CAS",
                },
                "CLAIMED": {
                    (True, False, False, False, False): None,
                    (True, True, False, False, False): "DELIVERY_ONLY",
                    (
                        True,
                        True,
                        True,
                        False,
                        False,
                    ): "DELIVERY_RECEIPT_PRE_CAS",
                },
                "DELIVERED": {
                    (True, True, True, False, False): None,
                    (True, True, True, True, False): "CONSUMPTION_ONLY",
                    (
                        True,
                        True,
                        True,
                        True,
                        True,
                    ): "CONSUMPTION_RECEIPT_PRE_CAS",
                },
                "CONSUMED": {
                    (True, True, True, True, True): None,
                },
            }
            tail_kind = allowed.get(status, {}).get(present, "INVALID")
            if tail_kind == "INVALID":
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_RECOVERY_TAIL_INVALID"
                )
            if (
                request is None
                or state.get("request_digest")
                != request.get(REQUEST_DIGEST_FIELD)
                or (
                    status in {"CLAIMED", "DELIVERED", "CONSUMED"}
                    and (
                        claim is None
                        or state.get("claim_digest")
                        != claim.get(CLAIM_DIGEST_FIELD)
                    )
                )
                or (
                    status in {"DELIVERED", "CONSUMED"}
                    and (
                        delivery_receipt is None
                        or state.get("delivery_receipt_digest")
                        != delivery_receipt.get(DELIVERY_RECEIPT_DIGEST_FIELD)
                    )
                )
                or (
                    status == "CONSUMED"
                    and (
                        consumption_receipt is None
                        or state.get("consumption_receipt_digest")
                        != consumption_receipt.get(
                            CONSUMPTION_RECEIPT_DIGEST_FIELD
                        )
                    )
                )
            ):
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_RECOVERY_CHECKPOINT_BINDING_INVALID"
                )
            materials = documents["input_materials"]
            return {
                "run_id": run_id,
                "cycle_index": cycle_index,
                "stage": stage,
                "stage_status": status,
                "checkpoint_digest": checkpoint[CHECKPOINT_DIGEST_FIELD],
                "mailbox_checkpoint": checkpoint,
                "request": request,
                "claim": claim,
                "agent_delivery": delivery,
                "delivery_receipt": delivery_receipt,
                "agent_consumption": consumption,
                "consumption_receipt": consumption_receipt,
                "canonical_packet_original": materials[
                    "canonical_packet_original"
                ],
                "lossless_context_package": materials[
                    "lossless_context_package"
                ],
                "ordered_agent_input_delivery_units": materials[
                    "ordered_delivery_units"
                ],
                "recovery_tail_kind": tail_kind,
                "read_only": True,
                "network_request_count": 0,
                "account_access": False,
                "order_submission": False,
                "agent_invocation_count": 0,
                "clock_read_count": 0,
                "executable": False,
            }

    def load_claimed_stage_snapshot(
        self, *, run_id: str, cycle_index: int, stage: str
    ) -> Mapping[str, Any]:
        """Reopen the unique historical CLAIMED checkpoint and its inputs."""

        if stage not in STAGES:
            raise V32CurrentRootAgentMailboxStoreError(
                "V32_MAILBOX_STORE_STAGE_INVALID"
            )
        with self._lock():
            documents = self._stage_documents(
                cycle_index=cycle_index, stage=stage
            )
            request = documents["request"]
            claim = documents["claim"]
            if request is None or claim is None:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CLAIMED_SNAPSHOT_INCOMPLETE"
                )
            request_digest = request[REQUEST_DIGEST_FIELD]
            claim_digest = claim[CLAIM_DIGEST_FIELD]
            history_root = self._safe_path(
                f"{self._base(cycle_index)}/checkpoints"
            )
            matches: list[Mapping[str, Any]] = []
            for path in sorted(history_root.glob("*.json")):
                checkpoint = self._load_canonical(path)
                try:
                    digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
                        checkpoint
                    )
                except (TypeError, ValueError) as exc:
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CHECKPOINT_HISTORY_INVALID"
                    ) from exc
                if (
                    path.name != f"{digest}.json"
                    or checkpoint.get("run_id") != run_id
                    or checkpoint.get("cycle_index") != cycle_index
                ):
                    raise V32CurrentRootAgentMailboxStoreError(
                        "V32_MAILBOX_STORE_CHECKPOINT_HISTORY_INVALID"
                    )
                state = checkpoint["stage_states"][stage]
                if (
                    state["status"] == "CLAIMED"
                    and state["request_digest"] == request_digest
                    and state["claim_digest"] == claim_digest
                ):
                    matches.append(checkpoint)
            if len(matches) != 1:
                raise V32CurrentRootAgentMailboxStoreError(
                    "V32_MAILBOX_STORE_CLAIMED_SNAPSHOT_INVALID"
                )
            return {
                "mailbox_checkpoint": matches[0],
                "request": request,
                "claim": claim,
                "lossless_context_package": documents["input_materials"][
                    "lossless_context_package"
                ],
                "read_only": True,
                "network_request_count": 0,
                "account_access": False,
                "order_submission": False,
                "executable": False,
            }


__all__ = [
    "LocalV32CurrentRootAgentMailbox",
    "STORE_ROOT",
    "V32CurrentRootAgentMailboxStoreError",
]
