from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2 import (
    v32_durable_json as durable_json_module,
)
from trade_system.theory_paper_v2.v32_durable_json import (
    atomic_replace_json,
    confirm_existing_json,
    exclusive_lock_file,
    write_once_directory,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.contracts.catalog import (
    build_canonical_manifest,
    schema_documents_from_manifest,
)
from trade_system.theory_paper_v2.infrastructure.contract_bundle import (
    FrozenManifestError,
    assert_byte_identical_trees,
    freeze_or_load_manifest,
    load_and_verify_frozen_manifest,
    materialize_contract_bundle,
)
from trade_system.theory_paper_v2.infrastructure.contract_bundle import (
    materialize as materialize_module,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "config" / "theory_agent_v2.canonical_contract_manifest.v1.json"
)
BUNDLE_PATH = ROOT / "agent-cluster" / "contracts"
NESTED_REGISTRY_NAMES = (
    "schema_registry",
    "object_owner_registry",
    "closed_error_registry",
    "closed_event_registry",
    "constraint_registry",
    "plugin_policy_registry",
)


class TheoryPaperV2ContractTests(unittest.TestCase):
    def test_v32_cleanup_preserves_primary_and_attempts_every_operation(self) -> None:
        calls: list[str] = []

        def fail(label: str) -> None:
            calls.append(label)
            raise OSError(f"cleanup:{label}")

        with self.assertRaisesRegex(OSError, "primary failure") as captured:
            try:
                raise OSError("primary failure")
            finally:
                durable_json_module._cleanup_preserving_primary(
                    [
                        ("FIRST", lambda: fail("first")),
                        ("SECOND", lambda: fail("second")),
                    ]
                )
        self.assertEqual(["first", "second"], calls)
        self.assertTrue(
            any("V32_DURABLE_CLEANUP_FAILURE:FIRST" in note for note in captured.exception.__notes__)
        )

        calls.clear()
        with self.assertRaisesRegex(OSError, "cleanup:first"):
            durable_json_module._cleanup_preserving_primary(
                [
                    ("FIRST", lambda: fail("first")),
                    ("SECOND", lambda: fail("second")),
                ]
            )
        self.assertEqual(["first", "second"], calls)

    def test_write_once_failure_before_publish_never_exposes_final_target(self) -> None:
        class InjectedHandleFailure:
            def __init__(self, handle: object, operation: str) -> None:
                self._handle = handle
                self._operation = operation

            def __enter__(self) -> "InjectedHandleFailure":
                self._handle.__enter__()
                return self

            def __exit__(self, *args: object) -> object:
                return self._handle.__exit__(*args)

            def write(self, payload: bytes) -> int:
                if self._operation == "write":
                    self._handle.write(payload[: max(1, len(payload) // 2)])
                    raise OSError("injected partial write failure")
                return self._handle.write(payload)

            def flush(self) -> None:
                if self._operation == "flush":
                    raise OSError("injected flush failure")
                self._handle.flush()

            def fileno(self) -> int:
                return self._handle.fileno()

        real_fdopen = durable_json_module.os.fdopen
        for operation in ("write", "flush"):
            with self.subTest(operation=operation):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    target = root / "receipt.json"

                    def failing_fdopen(*args: object, **kwargs: object) -> object:
                        return InjectedHandleFailure(
                            real_fdopen(*args, **kwargs), operation
                        )

                    with mock.patch.object(
                        durable_json_module.os,
                        "fdopen",
                        side_effect=failing_fdopen,
                    ):
                        with self.assertRaises(OSError):
                            write_once_json(target, {"value": operation})
                    self.assertFalse(target.exists())
                    self.assertEqual([], list(root.iterdir()))

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "receipt.json"
            with mock.patch.object(
                durable_json_module.os,
                "fsync",
                side_effect=OSError("injected fsync failure"),
            ):
                with self.assertRaises(OSError):
                    write_once_json(target, {"value": "fsync"})
            self.assertFalse(target.exists())
            self.assertEqual([], list(root.iterdir()))

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "receipt.json"
            calls = 0
            real_fsync = durable_json_module.os.fsync
            target_parent_stat = target.parent.stat()

            def fail_directory_fsync(descriptor: int) -> None:
                nonlocal calls
                descriptor_stat = durable_json_module.os.fstat(descriptor)
                is_target_parent = (
                    descriptor_stat.st_dev == target_parent_stat.st_dev
                    and descriptor_stat.st_ino == target_parent_stat.st_ino
                )
                if is_target_parent:
                    calls += 1
                if is_target_parent and target.exists():
                    raise OSError("injected directory fsync failure")
                real_fsync(descriptor)

            with mock.patch.object(
                durable_json_module.os,
                "fsync",
                side_effect=fail_directory_fsync,
            ), self.assertRaises(OSError):
                write_once_json(target, {"value": "directory-fsync"})
            self.assertEqual(
                canonical_bytes({"value": "directory-fsync"}) + b"\n",
                target.read_bytes(),
            )
            retry_calls = 0

            def count_retry_directory_fsync(descriptor: int) -> None:
                nonlocal retry_calls
                descriptor_stat = durable_json_module.os.fstat(descriptor)
                if (
                    descriptor_stat.st_dev == target_parent_stat.st_dev
                    and descriptor_stat.st_ino == target_parent_stat.st_ino
                ):
                    retry_calls += 1
                real_fsync(descriptor)

            with mock.patch.object(
                durable_json_module.os,
                "fsync",
                side_effect=count_retry_directory_fsync,
            ):
                self.assertEqual(
                    "EXISTING_IDENTICAL",
                    write_once_json(target, {"value": "directory-fsync"}),
                )
            self.assertEqual(2, retry_calls)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "receipt.json"
            with mock.patch.object(
                durable_json_module.os,
                "link",
                side_effect=OSError("injected publish failure"),
            ):
                with self.assertRaises(OSError):
                    write_once_json(target, {"value": "publish"})
            self.assertFalse(target.exists())
            self.assertEqual([], list(root.iterdir()))

    def test_write_once_atomic_publish_preserves_concurrent_semantics(self) -> None:
        def run_pair(left: dict[str, str], right: dict[str, str]) -> list[object]:
            barrier = threading.Barrier(2)

            def invoke(value: dict[str, str]) -> object:
                barrier.wait(timeout=5)
                try:
                    return write_once_json(target, value)
                except Exception as exc:  # Result is asserted below.
                    return exc

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(invoke, left),
                    executor.submit(invoke, right),
                )
                return [future.result(timeout=5) for future in futures]

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "same.json"
            same_results = run_pair({"value": "same"}, {"value": "same"})
            self.assertEqual(["CREATED", "EXISTING_IDENTICAL"], sorted(same_results))
            self.assertEqual(
                canonical_bytes({"value": "same"}) + b"\n",
                target.read_bytes(),
            )
            self.assertEqual([target], list(root.iterdir()))

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "different.json"
            different_results = run_pair({"value": "left"}, {"value": "right"})
            statuses = [item for item in different_results if isinstance(item, str)]
            failures = [item for item in different_results if isinstance(item, Exception)]
            self.assertEqual(["CREATED"], statuses)
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], CanonicalContractError)
            self.assertRegex(
                str(failures[0]),
                r"WRITE_ONCE_(?:CONFLICT|RACE)",
            )
            self.assertIn(
                target.read_bytes(),
                (
                    canonical_bytes({"value": "left"}) + b"\n",
                    canonical_bytes({"value": "right"}) + b"\n",
                ),
            )
            self.assertEqual([target], list(root.iterdir()))

    def test_v32_write_once_rejects_symlink_ancestors_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_DIRECTORY_UNSAFE"
            ):
                write_once_json(alias / "receipt.json", {"value": "unsafe"})
            self.assertFalse((real / "receipt.json").exists())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            source = root / "source.json"
            source.write_bytes(canonical_bytes({"value": "same"}) + b"\n")
            target = root / "receipt.json"
            target.symlink_to(source)
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_TARGET_UNSAFE"
            ):
                write_once_json(target, {"value": "same"})
            self.assertTrue(target.is_symlink())
            self.assertEqual(
                source.read_bytes(), canonical_bytes({"value": "same"}) + b"\n"
            )

    def test_v32_directory_retry_repairs_fsync_and_rejects_inode_swap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            durable_json_module.ensure_directory_tree(root)
            nested = root / "first" / "second"
            root_stat = root.stat()
            real_fsync = durable_json_module.os.fsync

            def fail_root_parent_entry(descriptor: int) -> None:
                descriptor_stat = durable_json_module.os.fstat(descriptor)
                if (
                    descriptor_stat.st_dev == root_stat.st_dev
                    and descriptor_stat.st_ino == root_stat.st_ino
                ):
                    raise OSError("injected parent fsync failure")
                real_fsync(descriptor)

            with mock.patch.object(
                durable_json_module.os,
                "fsync",
                side_effect=fail_root_parent_entry,
            ):
                with self.assertRaisesRegex(OSError, "parent fsync failure"):
                    durable_json_module.ensure_directory_tree(nested)
            self.assertTrue((root / "first").is_dir())
            self.assertFalse(nested.exists())

            calls = 0

            def count_fsync(descriptor: int) -> None:
                nonlocal calls
                calls += 1
                real_fsync(descriptor)

            with mock.patch.object(
                durable_json_module.os, "fsync", side_effect=count_fsync
            ):
                durable_json_module.ensure_directory_tree(nested)
            self.assertGreaterEqual(calls, 2)
            self.assertTrue(nested.is_dir())

            original = root / "first"
            moved = root / "first-original"
            original.rename(moved)
            original.mkdir()
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_DIRECTORY_IDENTITY_CHANGED"
            ):
                durable_json_module.ensure_directory_tree(original)

    def test_v32_write_once_rejects_parent_swap_after_publish_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            state = root / "state"
            durable_json_module.ensure_directory_tree(state)
            moved = root / "state-moved"
            target = state / "receipt.json"
            real_link = durable_json_module.os.link

            def publish_then_swap(*args: object, **kwargs: object) -> None:
                real_link(*args, **kwargs)
                state.rename(moved)
                state.mkdir()

            with mock.patch.object(
                durable_json_module.os,
                "link",
                side_effect=publish_then_swap,
            ):
                with self.assertRaisesRegex(
                    CanonicalContractError,
                    "WRITE_ONCE_(?:DIRECTORY_IDENTITY_CHANGED|POST_PUBLISH_VERIFY_FAILED)",
                ):
                    write_once_json(target, {"value": "created-before-swap"})
            self.assertFalse(target.exists())
            self.assertTrue((moved / "receipt.json").is_file())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            state = root / "state"
            target = state / "receipt.json"
            payload = {"value": "existing-before-swap"}
            write_once_json(target, payload)
            moved = root / "state-moved"
            real_read = durable_json_module._read_regular_file_at
            swapped = False

            def read_then_swap(parent_fd: int, name: str) -> bytes:
                nonlocal swapped
                result = real_read(parent_fd, name)
                if not swapped:
                    swapped = True
                    state.rename(moved)
                    state.mkdir()
                    (state / "receipt.json").write_bytes(result)
                return result

            with mock.patch.object(
                durable_json_module,
                "_read_regular_file_at",
                side_effect=read_then_swap,
            ):
                with self.assertRaisesRegex(
                    CanonicalContractError,
                    "WRITE_ONCE_(?:DIRECTORY_IDENTITY_CHANGED|POST_PUBLISH_VERIFY_FAILED)",
                ):
                    write_once_json(target, payload)

    def test_v32_confirm_existing_never_creates_and_durably_checks_exact_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw).resolve() / "receipt.json"
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_TARGET_MISSING"
            ):
                confirm_existing_json(target, {"value": "missing"})
            self.assertFalse(target.exists())

            write_once_json(target, {"value": "sealed"})
            confirm_existing_json(target, {"value": "sealed"})
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_CONFLICT"
            ):
                confirm_existing_json(target, {"value": "different"})

    def test_v32_exclusive_lock_rejects_leaf_and_ancestor_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            external = root / "external.lock"
            external.write_bytes(b"unchanged")
            leaf = root / "store.lock"
            leaf.symlink_to(external)
            with self.assertRaisesRegex(
                CanonicalContractError, "V32_LOCK_TARGET_UNSAFE"
            ):
                with exclusive_lock_file(leaf):
                    self.fail("symlink lock must never be acquired")
            self.assertEqual(b"unchanged", external.read_bytes())

            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_DIRECTORY_UNSAFE"
            ):
                with exclusive_lock_file(alias / "store.lock"):
                    self.fail("symlink ancestor lock must never be acquired")
            self.assertFalse((real / "store.lock").exists())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            lock = root / "store.lock"
            moved = root / "store-original.lock"
            real_flock = durable_json_module.fcntl.flock
            swapped = False

            def flock_then_swap(descriptor: int, operation: int) -> None:
                nonlocal swapped
                real_flock(descriptor, operation)
                if operation == durable_json_module.fcntl.LOCK_EX and not swapped:
                    swapped = True
                    lock.rename(moved)
                    lock.write_bytes(b"replacement")

            with mock.patch.object(
                durable_json_module.fcntl,
                "flock",
                side_effect=flock_then_swap,
            ):
                with self.assertRaisesRegex(
                    CanonicalContractError, "V32_LOCK_POST_OPEN_VERIFY_FAILED"
                ):
                    with exclusive_lock_file(lock):
                        self.fail("replaced lock must never guard the critical section")

    def test_v32_atomic_replace_rejects_parent_swap_after_replace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            state = root / "state"
            durable_json_module.ensure_directory_tree(state)
            target = state / "checkpoint.json"
            atomic_replace_json(target, {"revision": 0})
            self.assertEqual(
                canonical_bytes({"revision": 0}) + b"\n", target.read_bytes()
            )

            moved = root / "state-moved"
            real_replace = durable_json_module.os.replace

            def replace_then_swap(*args: object, **kwargs: object) -> None:
                real_replace(*args, **kwargs)
                state.rename(moved)
                state.mkdir()

            with mock.patch.object(
                durable_json_module.os,
                "replace",
                side_effect=replace_then_swap,
            ):
                with self.assertRaisesRegex(
                    CanonicalContractError,
                    "WRITE_ONCE_(?:DIRECTORY_IDENTITY_CHANGED|POST_PUBLISH_VERIFY_FAILED)",
                ):
                    atomic_replace_json(target, {"revision": 1})
            self.assertFalse(target.exists())
            self.assertEqual(
                canonical_bytes({"revision": 1}) + b"\n",
                (moved / "checkpoint.json").read_bytes(),
            )

    def test_v32_write_once_directory_is_exact_and_rejects_parent_swap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            state = root / "state"
            durable_json_module.ensure_directory_tree(state)
            target = state / "bundle"
            files = {"capture.json": b"{}\n", "raw.bin": b"raw"}
            self.assertEqual("CREATED", write_once_directory(target, files))
            self.assertEqual(
                "EXISTING_IDENTICAL", write_once_directory(target, files)
            )
            with self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_DIRECTORY_CONFLICT"
            ):
                write_once_directory(
                    target, {"capture.json": b"{}\n", "raw.bin": b"drift"}
                )

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            state = root / "state"
            durable_json_module.ensure_directory_tree(state)
            target = state / "bundle"
            moved = root / "state-moved"
            real_activate = durable_json_module.rename_directory_noreplace_at
            real_rename = durable_json_module.os.rename

            def rename_then_swap(**kwargs: object) -> None:
                real_activate(**kwargs)
                real_rename(state, moved)
                state.mkdir()

            with mock.patch.object(
                durable_json_module,
                "rename_directory_noreplace_at",
                side_effect=rename_then_swap,
            ):
                with self.assertRaisesRegex(
                    CanonicalContractError,
                    "WRITE_ONCE_DIRECTORY_(?:IDENTITY_CHANGED|POST_PUBLISH_VERIFY_FAILED|TARGET_UNSAFE)",
                ):
                    write_once_directory(target, {"raw.bin": b"sealed"})
            self.assertFalse(target.exists())
            self.assertEqual(b"sealed", (moved / "bundle/raw.bin").read_bytes())

    def test_v32_write_once_directory_does_not_replace_raced_empty_final(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            target = root / "state/bundle"
            real_activate = durable_json_module.rename_directory_noreplace_at

            def install_empty_final_then_activate(**kwargs: object) -> None:
                durable_json_module.os.mkdir(
                    str(kwargs["destination_name"]),
                    dir_fd=int(kwargs["destination_parent_fd"]),
                )
                real_activate(**kwargs)

            with mock.patch.object(
                durable_json_module,
                "rename_directory_noreplace_at",
                side_effect=install_empty_final_then_activate,
            ), self.assertRaisesRegex(
                CanonicalContractError, "WRITE_ONCE_DIRECTORY_CONFLICT"
            ):
                write_once_directory(target, {"raw.bin": b"must-not-overwrite"})

            self.assertTrue(target.is_dir())
            self.assertEqual([], list(target.iterdir()))
            self.assertEqual(
                [],
                list(target.parent.glob(".v32-write-once-directory-*.tmp")),
            )

    def test_v32_directory_noreplace_unavailable_platform_fails_closed(self) -> None:
        with mock.patch.object(
            durable_json_module, "_RENAMEATX_NP", None
        ), mock.patch.object(
            durable_json_module.sys, "platform", "unsupported-test-platform"
        ), self.assertRaisesRegex(
            CanonicalContractError,
            "V32_DIRECTORY_NOREPLACE_RENAME_UNAVAILABLE",
        ):
            durable_json_module.rename_directory_noreplace_at(
                source_parent_fd=0,
                source_name="private-stage",
                destination_parent_fd=0,
                destination_name="final",
            )

    def test_v32_write_once_directory_serializes_concurrent_writers(self) -> None:
        def run_pair(
            target: Path,
            left: dict[str, bytes],
            right: dict[str, bytes],
        ) -> list[object]:
            barrier = threading.Barrier(2)

            def invoke(files: dict[str, bytes]) -> object:
                barrier.wait(timeout=5)
                try:
                    return write_once_directory(target, files)
                except Exception as exc:  # Result is asserted below.
                    return exc

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(invoke, left),
                    executor.submit(invoke, right),
                )
                return [future.result(timeout=5) for future in futures]

        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "same"
            files = {"raw.bin": b"same"}
            self.assertEqual(
                ["CREATED", "EXISTING_IDENTICAL"],
                sorted(run_pair(target, files, files)),
            )

        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "different"
            results = run_pair(
                target,
                {"raw.bin": b"left"},
                {"raw.bin": b"right"},
            )
            successes = [row for row in results if isinstance(row, str)]
            failures = [row for row in results if isinstance(row, Exception)]
            self.assertEqual(["CREATED"], successes)
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], CanonicalContractError)
            self.assertIn(
                (target / "raw.bin").read_bytes(),
                {b"left", b"right"},
            )

    def test_frozen_manifest_matches_bootstrap_catalog_exactly(self) -> None:
        frozen = load_and_verify_frozen_manifest(MANIFEST_PATH)
        bootstrap = build_canonical_manifest()
        self.assertEqual(canonical_bytes(frozen), canonical_bytes(bootstrap))

    def test_manifest_and_every_nested_registry_self_digest_verify(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        self.assertEqual(
            verify_self_digest(manifest, "manifest_digest"),
            manifest["manifest_digest"],
        )
        for registry_name in NESTED_REGISTRY_NAMES:
            registry = manifest[registry_name]
            self.assertEqual(
                verify_self_digest(registry, "registry_digest"),
                registry["registry_digest"],
            )

    def test_schema_identity_set_is_closed_and_materialized(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        entries = manifest["schema_registry"]["entries"]
        registered = {entry["schema_id"] for entry in entries}
        rendered = {
            schema_id for schema_id, _ in schema_documents_from_manifest(manifest)
        }
        materialized = {
            path.name.removesuffix(".schema.json")
            for path in (BUNDLE_PATH / "schemas").glob("*.schema.json")
        }
        self.assertEqual(142, len(registered))
        self.assertEqual(registered, rendered)
        self.assertEqual(registered, materialized)
        self.assertNotIn("stage_activation_receipt", registered)

    def test_all_schemas_are_closed_objects(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        for schema_id, document in schema_documents_from_manifest(manifest):
            with self.subTest(schema_id=schema_id):
                self.assertEqual("object", document["type"])
                self.assertIs(document["additionalProperties"], False)
                self.assertTrue(set(document["required"]).issubset(document["properties"]))

    def test_action_intents_have_no_e0_suffix(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        values = manifest["closed_enums"]["ActionIntent"]
        self.assertEqual(
            [
                "KEEP_CORE",
                "ACTIVATE_REGISTERED_STAGE",
                "REDUCE_TACTICAL",
                "PARTIAL_PROFIT",
                "EXIT_STRATEGIC",
                "EXIT_TO_REENTRY_PENDING",
                "REENTER_PARTIAL",
                "NO_ACTION_WITH_OBLIGATION",
            ],
            values,
        )
        self.assertFalse(any(value.endswith("_E0") for value in values))

    def test_object_owner_registry_has_unique_registered_payloads(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        registered = {
            entry["schema_id"]
            for entry in manifest["schema_registry"]["entries"]
        }
        owner_ids = [
            entry["object_schema_id"]
            for entry in manifest["object_owner_registry"]["entries"]
        ]
        self.assertEqual(135, len(owner_ids))
        self.assertEqual(len(owner_ids), len(set(owner_ids)))
        self.assertTrue(set(owner_ids).issubset(registered))

    def test_e0_plugin_registry_is_empty_and_permissionless(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        plugin = manifest["plugin_policy_registry"]
        self.assertEqual([], plugin["entries"])
        self.assertEqual([], plugin["required_plugin_ids"])
        self.assertEqual([], plugin["optional_plugin_ids"])
        self.assertEqual(
            {
                "network": "DENIED",
                "filesystem": "DENIED",
                "process": "DENIED",
                "environment": "DENIED",
                "ambient_clock": "DENIED",
                "randomness": "DENIED",
            },
            plugin["environment_permissions"],
        )

    def test_unit_of_work_committed_is_post_commit_only(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        entries = [
            entry
            for entry in manifest["closed_event_registry"]["entries"]
            if entry["event_type"] == "UNIT_OF_WORK_COMMITTED"
        ]
        self.assertEqual(1, len(entries))
        self.assertEqual("POST_COMMIT_NOTIFICATION", entries[0]["trigger_class"])
        self.assertIs(entries[0]["same_batch_commit_receipt_reference"], False)
        self.assertEqual(
            "FORBIDDEN",
            manifest["event_name_resolution"][
                "same_batch_commit_receipt_reference"
            ],
        )

    def test_strict_loader_rejects_float_duplicate_and_nonfinite(self) -> None:
        payloads = (
            b'{"value":1.5}\\n',
            b'{"value":1,"value":2}\\n',
            b'{"value":NaN}\\n',
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for index, payload in enumerate(payloads):
                with self.subTest(index=index):
                    path = root / f"{index}.json"
                    path.write_bytes(payload)
                    with self.assertRaises(CanonicalContractError):
                        load_json_strict(path)

    def test_ordinary_mode_never_rebuilds_catalog(self) -> None:
        with mock.patch.object(
            materialize_module,
            "build_canonical_manifest",
            side_effect=AssertionError("ordinary mode rebuilt catalog"),
        ):
            manifest, status = freeze_or_load_manifest(
                MANIFEST_PATH,
                freeze_manifest=False,
            )
        self.assertEqual("READ_ONLY_EXISTING", status)
        self.assertEqual(
            "THEORY_AGENT_V2_CANONICAL_CONTRACT_MANIFEST",
            manifest["manifest_id"],
        )

    def test_explicit_freeze_is_write_once_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "manifest.json"
            first, first_status = freeze_or_load_manifest(
                target,
                freeze_manifest=True,
            )
            second, second_status = freeze_or_load_manifest(
                target,
                freeze_manifest=True,
            )
        self.assertEqual("CREATED", first_status)
        self.assertEqual("EXISTING_IDENTICAL", second_status)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

    def test_nested_registry_digest_is_independently_enforced(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        manifest["constraint_registry"]["entries"][0]["constraint_id"] = (
            "TAMPERED_CONSTRAINT"
        )
        manifest = self_digest(manifest, "manifest_digest")
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "tampered.json"
            target.write_bytes(canonical_bytes(manifest) + b"\n")
            with self.assertRaisesRegex(
                FrozenManifestError,
                "NESTED_REGISTRY_DIGEST_INVALID:constraint_registry",
            ):
                load_and_verify_frozen_manifest(target)

    def test_two_isolated_materializations_are_byte_identical(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as left_raw:
            with tempfile.TemporaryDirectory() as right_raw:
                left = Path(left_raw)
                right = Path(right_raw)
                left_result = materialize_contract_bundle(manifest, left)
                right_result = materialize_contract_bundle(manifest, right)
                self.assertEqual(
                    left_result.bundle_index_digest,
                    right_result.bundle_index_digest,
                )
                self.assertEqual(
                    left_result.file_count,
                    assert_byte_identical_trees(left, right),
                )

    def test_project_bundle_matches_fresh_materialization(self) -> None:
        manifest = load_and_verify_frozen_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as raw:
            fresh = Path(raw)
            materialize_contract_bundle(manifest, fresh)
            self.assertEqual(
                len(
                    [
                        path
                        for path in BUNDLE_PATH.rglob("*")
                        if path.is_file()
                    ]
                ),
                assert_byte_identical_trees(BUNDLE_PATH, fresh),
            )


if __name__ == "__main__":
    unittest.main()
