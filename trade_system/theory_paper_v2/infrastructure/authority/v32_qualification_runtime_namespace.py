"""Physical, per-identity runtime namespace for V3.2 qualification.

The namespace is derived only from a validated qualification identity.  Every
existing parent component is checked with ``lstat`` so a symlink is rejected
without resolving or opening its target.  Directory creation is followed by a
second complete component and tree verification.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping

from ...domain.governance.v32_qualification_identity import (
    TOMBSTONED_V32_RUN_IDS,
    V32QualificationIdentityError,
    validate_v32_run_id_syntax_v1,
)


class V32QualificationRuntimeNamespaceError(ValueError):
    """A qualification runtime namespace is missing, aliased, or malformed."""


RUNTIME_BASE = ".runtime/v32/qualifications"
_PATH_KEYS = (
    "root",
    "evidence",
    "controller",
    "source",
    "run_source",
    "mailbox",
    "probe",
    "material",
)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC


def build_v32_qualification_runtime_paths_v1(
    qualification_run_id: Any,
) -> dict[str, str]:
    try:
        qualification = validate_v32_run_id_syntax_v1(qualification_run_id)
    except V32QualificationIdentityError as exc:
        raise V32QualificationRuntimeNamespaceError(str(exc)) from exc
    root = f"{RUNTIME_BASE}/{qualification}"
    return {
        "root": root,
        "evidence": f"{root}/evidence",
        "controller": f"{root}/controller",
        "source": f"{root}/public-source",
        "run_source": f"{root}/admitted-source",
        "mailbox": f"{root}/mailbox",
        "probe": f"{root}/monitor-probe",
        "material": f"{root}/material",
    }


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_PROJECT_ROOT_INVALID"
            )
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_PROJECT_ROOT_INVALID"
        )
    return root


def _component_state(path: Path) -> str:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return "MISSING"
    except OSError as exc:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
        ) from exc
    if stat.S_ISLNK(mode):
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_SYMLINK_FORBIDDEN"
        )
    if not stat.S_ISDIR(mode):
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
        )
    return "DIRECTORY"


def _component_paths(project: Path, relative_root: str) -> tuple[Path, ...]:
    current = project
    paths: list[Path] = []
    for part in PurePosixPath(relative_root).parts:
        current = current / part
        paths.append(current)
    return tuple(paths)


def _verify_components(
    project: Path, relative_root: str, *, require_root: bool
) -> tuple[Path, ...]:
    paths = _component_paths(project, relative_root)
    missing_seen = False
    for path in paths:
        state = _component_state(path)
        if state == "MISSING":
            missing_seen = True
            continue
        elif missing_seen:
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
            )
    if require_root and missing_seen:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_MISSING"
        )
    return paths


def _verify_tree(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            child = current_path / name
            try:
                mode = os.lstat(child).st_mode
            except OSError as exc:
                raise V32QualificationRuntimeNamespaceError(
                    "V32_QUALIFICATION_NAMESPACE_TREE_INVALID"
                ) from exc
            if stat.S_ISLNK(mode):
                raise V32QualificationRuntimeNamespaceError(
                    "V32_QUALIFICATION_NAMESPACE_SYMLINK_FORBIDDEN"
                )


def _reopen_verify_and_sync_components(
    project: Path,
    *,
    parts: tuple[str, ...],
    identities: tuple[tuple[int, int], ...],
) -> None:
    """Reopen the lexical chain, verify inode identity, and repair every dentry."""

    descriptor: int | None = None
    try:
        descriptor = os.open(project, _DIRECTORY_OPEN_FLAGS)
        for part, expected in zip(parts, identities, strict=True):
            next_descriptor = os.open(
                part, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
            )
            observed = os.fstat(next_descriptor)
            if (observed.st_dev, observed.st_ino) != expected:
                os.close(next_descriptor)
                raise V32QualificationRuntimeNamespaceError(
                    "V32_QUALIFICATION_NAMESPACE_IDENTITY_CHANGED"
                )
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except V32QualificationRuntimeNamespaceError:
        raise
    except OSError as exc:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def assert_v32_qualification_runtime_namespace_v1(
    *,
    project_root: Path,
    qualification_run_id: Any,
    require_root: bool,
) -> Mapping[str, str]:
    project = _project_root(project_root)
    paths = build_v32_qualification_runtime_paths_v1(qualification_run_id)
    components = _verify_components(
        project, paths["root"], require_root=require_root
    )
    if require_root:
        runtime_root = components[-1]
        try:
            if runtime_root.resolve(strict=True) != runtime_root:
                raise V32QualificationRuntimeNamespaceError(
                    "V32_QUALIFICATION_NAMESPACE_ALIAS_FORBIDDEN"
                )
        except (OSError, ValueError) as exc:
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
            ) from exc
        _verify_tree(runtime_root)
    return paths


def assert_v32_qualification_runtime_root_components_v1(
    *, project_root: Path, qualification_run_id: Any
) -> Mapping[str, str]:
    """Verify the prepared lexical root without scanning its mutable tree.

    This narrow pre-lock check exists so a composition contender can confirm
    that Phase A created the exact run root before it waits on the external
    run lock.  A complete tree replay still runs after the lock is acquired;
    doing it before the lock would race write-once temporary publications.
    """

    project = _project_root(project_root)
    paths = build_v32_qualification_runtime_paths_v1(qualification_run_id)
    components = _verify_components(project, paths["root"], require_root=True)
    runtime_root = components[-1]
    try:
        if runtime_root.resolve(strict=True) != runtime_root:
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_ALIAS_FORBIDDEN"
            )
    except (OSError, ValueError) as exc:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
        ) from exc
    return paths


def create_v32_qualification_runtime_namespace_v1(
    *, project_root: Path, qualification_run_id: Any
) -> Mapping[str, str]:
    try:
        qualification = validate_v32_run_id_syntax_v1(qualification_run_id)
    except V32QualificationIdentityError as exc:
        raise V32QualificationRuntimeNamespaceError(str(exc)) from exc
    if qualification in TOMBSTONED_V32_RUN_IDS:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_RUN_ID_TOMBSTONED"
        )
    project = _project_root(project_root)
    paths = build_v32_qualification_runtime_paths_v1(qualification)
    components = _verify_components(project, paths["root"], require_root=False)
    final_state = _component_state(components[-1])
    recover_empty_root = False
    if final_state != "MISSING":
        try:
            recover_empty_root = not any(components[-1].iterdir())
        except OSError as exc:
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
            ) from exc
        if not recover_empty_root:
            raise V32QualificationRuntimeNamespaceError(
                "V32_QUALIFICATION_NAMESPACE_ALREADY_EXISTS"
            )
    if not _NOFOLLOW or not _DIRECTORY:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_SECURE_DIRFD_UNAVAILABLE"
        )
    descriptor: int | None = None
    identities: list[tuple[int, int]] = []
    try:
        descriptor = os.open(project, _DIRECTORY_OPEN_FLAGS)
        parts = tuple(PurePosixPath(paths["root"]).parts)
        for index, part in enumerate(parts):
            created = False
            try:
                next_descriptor = os.open(
                    part,
                    _DIRECTORY_OPEN_FLAGS,
                    dir_fd=descriptor,
                )
                if index == len(parts) - 1:
                    if not recover_empty_root or os.listdir(next_descriptor):
                        os.close(next_descriptor)
                        raise V32QualificationRuntimeNamespaceError(
                            "V32_QUALIFICATION_NAMESPACE_CREATION_RACE"
                        )
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    created = True
                except FileExistsError:
                    if index == len(parts) - 1:
                        raise V32QualificationRuntimeNamespaceError(
                            "V32_QUALIFICATION_NAMESPACE_CREATION_RACE"
                        )
                next_descriptor = os.open(
                    part,
                    _DIRECTORY_OPEN_FLAGS,
                    dir_fd=descriptor,
                )
            if not stat.S_ISDIR(os.fstat(next_descriptor).st_mode):
                os.close(next_descriptor)
                raise V32QualificationRuntimeNamespaceError(
                    "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
                )
            observed = os.fstat(next_descriptor)
            identities.append((observed.st_dev, observed.st_ino))
            # This fsync belongs to the still-open parent descriptor and is
            # required even for an existing winner so a retry repairs a prior
            # mkdir whose directory-entry sync response was lost.
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
            if created:
                # Mandatory post-create proof is anchored to the parent fd;
                # no lexical component can be swapped to a symlink here.
                if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise V32QualificationRuntimeNamespaceError(
                        "V32_QUALIFICATION_NAMESPACE_COMPONENT_INVALID"
                    )
        _reopen_verify_and_sync_components(
            project,
            parts=parts,
            identities=tuple(identities),
        )
    except V32QualificationRuntimeNamespaceError:
        raise
    except OSError as exc:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_CREATE_FAILED"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return assert_v32_qualification_runtime_namespace_v1(
        project_root=project,
        qualification_run_id=qualification_run_id,
        require_root=True,
    )


def assert_v32_qualification_runtime_paths_exact_v1(
    *, qualification_run_id: Any, paths: Mapping[str, Any]
) -> dict[str, str]:
    expected = build_v32_qualification_runtime_paths_v1(qualification_run_id)
    if not isinstance(paths, Mapping) or tuple(paths) != _PATH_KEYS or dict(paths) != expected:
        raise V32QualificationRuntimeNamespaceError(
            "V32_QUALIFICATION_NAMESPACE_PATH_SET_INVALID"
        )
    return expected


__all__ = [
    "RUNTIME_BASE",
    "V32QualificationRuntimeNamespaceError",
    "assert_v32_qualification_runtime_namespace_v1",
    "assert_v32_qualification_runtime_root_components_v1",
    "assert_v32_qualification_runtime_paths_exact_v1",
    "build_v32_qualification_runtime_paths_v1",
    "create_v32_qualification_runtime_namespace_v1",
]
