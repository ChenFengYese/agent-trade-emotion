"""Fixed runner and physical replay for V3.2 post-commit regression evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import platform
import selectors
import signal
import stat
import subprocess
import time
from typing import Any, Mapping

from ...application.v31_authority_freeze import document_binding
from ...domain.contracts.canonical import canonical_bytes
from ...domain.governance.v32_postcommit_regression import (
    AGGREGATE_DIGEST_FIELD,
    AGGREGATE_SCHEMA_ID,
    EXECUTION_DIGEST_FIELD,
    EXECUTION_SCHEMA_ID,
    FIXED_ENVIRONMENT,
    FIXED_GIT_EXECUTABLE,
    FIXED_MAX_STREAM_BYTES,
    FIXED_PYTHON_EXECUTABLE,
    FIXED_TIMEOUT_SECONDS,
    RESERVATION_DIGEST_FIELD,
    RESERVATION_SCHEMA_ID,
    SUITE_IDS,
    V32PostCommitRegressionError,
    build_v32_postcommit_regression_aggregate_support_v1,
    build_v32_postcommit_regression_execution_receipt_v1,
    build_v32_postcommit_regression_reservation_v1,
    fixed_argv_for_suite_v1,
    prequalification_paths_v1,
    qualification_support_paths_v1,
    verify_v32_postcommit_regression_aggregate_support_v1,
    verify_v32_postcommit_regression_execution_receipt_v1,
    verify_v32_postcommit_regression_reservation_v1,
)
from ...domain.governance.v32_qualification_identity import (
    V32QualificationIdentityError,
    validate_v32_active_qualification_identity_v1,
)
from .v32_secure_write_once_store import (
    V32SecureWriteOnceStoreError,
    secure_binding_for_existing_document,
    secure_load_json_document,
    secure_read_bytes,
    secure_write_once_json,
)


class V32PostCommitRegressionInfrastructureError(ValueError):
    """The fixed runner or a physical replay failed closed."""


_ALLOWED_UNTRACKED_USER_ARTIFACTS = (
    "archive/user-preserved/THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md",
)
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)


def _root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V32PostCommitRegressionInfrastructureError(
                "V32_POSTCOMMIT_PROJECT_ROOT_INVALID"
            )
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PROJECT_ROOT_INVALID"
        )
    return root


def _ids(target_run_id: str, qualification_run_id: str) -> tuple[str, str]:
    try:
        target, qualification = validate_v32_active_qualification_identity_v1(
            target_run_id=target_run_id,
            qualification_run_id=qualification_run_id,
        )
    except V32QualificationIdentityError as exc:
        raise V32PostCommitRegressionInfrastructureError(str(exc)) from exc
    if target.rsplit("-", 1)[-1] != qualification.rsplit("-", 1)[-1]:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_IDENTITY_PAIR_INVALID"
        )
    return target, qualification


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            [FIXED_GIT_EXECUTABLE, "-C", str(root), *args],
            check=True,
            capture_output=True,
            env=dict(FIXED_ENVIRONMENT),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_GIT_COMMAND_FAILED"
        ) from exc
    return result.stdout if binary else result.stdout.decode("utf-8", errors="strict").strip()


def _git_identity(root: Path) -> dict[str, str]:
    toplevel = _git(root, "rev-parse", "--show-toplevel")
    branch = _git(root, "branch", "--show-current")
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "show", "-s", "--format=%T", "HEAD")
    if toplevel != str(root) or not isinstance(branch, str) or not branch:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_GIT_IDENTITY_INVALID"
        )
    return {"branch": str(branch), "frozen_commit_sha": str(commit), "frozen_tree_sha": str(tree)}


def _allowed_artifacts(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative in _ALLOWED_UNTRACKED_USER_ARTIFACTS:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise V32PostCommitRegressionInfrastructureError(
                "V32_POSTCOMMIT_ALLOWED_USER_ARTIFACT_INVALID"
            )
        rows.append(
            {
                "relative_ref": relative,
                "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return rows


def _workspace_observation(root: Path) -> tuple[bytes, list[dict[str, str]], bool]:
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=no",
        binary=True,
    )
    assert isinstance(status, bytes)
    artifacts = _allowed_artifacts(root)
    allowed = {row["relative_ref"]: row["physical_sha256"] for row in artifacts}
    seen: set[str] = set()
    clean = True
    for entry in (row for row in status.split(b"\0") if row):
        try:
            state = entry[:2].decode("ascii")
            relative = entry[3:].decode("utf-8", errors="strict")
        except UnicodeError:
            clean = False
            continue
        path = root / relative
        if (
            state != "??"
            or relative not in allowed
            or relative in seen
            or path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != allowed[relative]
        ):
            clean = False
        seen.add(relative)
    if seen != set(allowed):
        clean = False
    return status, artifacts, clean


def _python_identity() -> tuple[str, str, str, str, bool]:
    supplied = Path(FIXED_PYTHON_EXECUTABLE)
    try:
        realpath = supplied.resolve(strict=True)
        physical = hashlib.sha256(realpath.read_bytes()).hexdigest()
        same = supplied.is_file() and Path(os.path.realpath(os.sys.executable)).samefile(realpath)
    except (OSError, ValueError):
        realpath = supplied
        physical = hashlib.sha256(b"V32_POSTCOMMIT_PYTHON_UNAVAILABLE").hexdigest()
        same = False
    return (
        FIXED_PYTHON_EXECUTABLE,
        realpath.as_posix(),
        physical,
        platform.python_version(),
        same,
    )


def _planned_binding(path: str, document: Mapping[str, Any], digest_field: str) -> dict[str, str]:
    binding = document_binding(path=path, document=document, digest_field=digest_field)
    return {
        **binding,
        "physical_sha256": hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest(),
    }


def _bounded_utf8(value: bytes | str | None) -> tuple[str, bool]:
    if value is None:
        payload = b""
    elif isinstance(value, str):
        payload = value.encode("utf-8", errors="strict")
    else:
        payload = bytes(value)
    complete = len(payload) <= FIXED_MAX_STREAM_BYTES
    bounded = payload if complete else payload[:FIXED_MAX_STREAM_BYTES]
    try:
        return bounded.decode("utf-8", errors="strict"), complete
    except UnicodeDecodeError:
        # An invalid UTF-8 subprocess stream can never support PASS.  Preserve
        # the complete bounded bytes losslessly as escaped Unicode codepoints.
        return bounded.decode("utf-8", errors="backslashreplace"), False


@dataclass(frozen=True)
class _BoundedSuiteRunResult:
    outcome: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    stdout_complete: bool
    stderr_complete: bool


def _run_fixed_suite_bounded(root: Path, suite_id: str) -> _BoundedSuiteRunResult:
    """Run one fixed suite with hard in-memory and pipe-consumption bounds."""

    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = False
    timed_out = False
    descendant_leak = False
    group_control_failed = False
    forced_drain_deadline: float | None = None
    post_exit_drain_deadline: float | None = None

    def terminate_group() -> None:
        nonlocal forced_drain_deadline, group_control_failed
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            group_control_failed = True
        if forced_drain_deadline is None:
            forced_drain_deadline = time.monotonic() + 2.0

    def unregister_all() -> None:
        for key in tuple(selector.get_map().values()):
            try:
                selector.unregister(key.fileobj)
            except (KeyError, ValueError):
                pass

    def capture_ready(timeout: float) -> None:
        nonlocal overflow
        for key, _ in selector.select(timeout=max(0.0, timeout)):
            try:
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            target = buffers[str(key.data)]
            available = FIXED_MAX_STREAM_BYTES + 1 - len(target)
            if available > 0:
                target.extend(chunk[:available])
            if len(chunk) > available or len(target) > FIXED_MAX_STREAM_BYTES:
                if not overflow:
                    overflow = True
                    terminate_group()

    def bounded_cleanup() -> None:
        """Kill the whole session, retain a bounded prefix, and never wait forever."""

        nonlocal group_control_failed
        terminate_group()
        cleanup_deadline = time.monotonic() + 2.0
        while selector.get_map() and time.monotonic() < cleanup_deadline:
            try:
                capture_ready(min(0.05, cleanup_deadline - time.monotonic()))
            except BaseException:
                break
        unregister_all()
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=max(0.01, cleanup_deadline - time.monotonic()))
            except BaseException:
                group_control_failed = True

    try:
        process = subprocess.Popen(
            fixed_argv_for_suite_v1(suite_id),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(FIXED_ENVIRONMENT),
            start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise OSError("V32_POSTCOMMIT_PIPE_REQUIRED")
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + FIXED_TIMEOUT_SECONDS
        while True:
            now = time.monotonic()
            direct_alive = process.poll() is None
            pipes_open = bool(selector.get_map())
            if direct_alive and now >= deadline and not timed_out:
                timed_out = True
                terminate_group()
            if not direct_alive and pipes_open and post_exit_drain_deadline is None:
                post_exit_drain_deadline = now + 2.0
            if (
                post_exit_drain_deadline is not None
                and pipes_open
                and now >= post_exit_drain_deadline
                and forced_drain_deadline is None
            ):
                descendant_leak = True
                terminate_group()
            if forced_drain_deadline is not None and now >= forced_drain_deadline:
                unregister_all()
                break
            if not direct_alive and not pipes_open:
                break

            wake_at = now + 0.1
            if direct_alive:
                wake_at = min(wake_at, deadline)
            if post_exit_drain_deadline is not None:
                wake_at = min(wake_at, post_exit_drain_deadline)
            if forced_drain_deadline is not None:
                wake_at = min(wake_at, forced_drain_deadline)
            delay = max(0.0, wake_at - time.monotonic())
            if selector.get_map():
                capture_ready(delay)
            elif delay > 0:
                # EOF on both pipes is not process completion.  Keep polling
                # the same hard deadline instead of falling into wait().
                time.sleep(delay)

        if process.poll() is None:
            terminate_group()
            try:
                process.wait(timeout=2.0)
            except (subprocess.TimeoutExpired, OSError):
                group_control_failed = True
        return_code = process.returncode
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            descendant_leak = True
            group_control_failed = True
        else:
            # EOF is not proof that a descendant did not close its inherited
            # pipes and continue mutating the worktree.  The process group
            # itself must be empty before PASS is even syntactically possible.
            descendant_leak = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                group_control_failed = True
        if overflow:
            return _BoundedSuiteRunResult(
                "OUTPUT_LIMIT_EXCEEDED", return_code,
                bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
            )
        if timed_out:
            return _BoundedSuiteRunResult(
                "TIMEOUT", None,
                bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
            )
        if group_control_failed:
            return _BoundedSuiteRunResult(
                "RUNNER_ERROR", None,
                bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
            )
        if descendant_leak:
            return _BoundedSuiteRunResult(
                "DESCENDANT_PROCESS_LEAK", None,
                bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
            )
        return _BoundedSuiteRunResult(
            "COMPLETED", return_code,
            bytes(buffers["stdout"]), bytes(buffers["stderr"]), True, True
        )
    except KeyboardInterrupt:
        bounded_cleanup()
        return _BoundedSuiteRunResult(
            "INTERRUPTED", None,
            bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        bounded_cleanup()
        return _BoundedSuiteRunResult(
            "RUNNER_ERROR", None,
            bytes(buffers["stdout"]), bytes(buffers["stderr"]), False, False
        )
    except BaseException:
        bounded_cleanup()
        raise
    finally:
        selector.close()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _write_execution_receipt(
    root: Path,
    *,
    paths: Mapping[str, str],
    reservation: Mapping[str, Any],
    suite_id: str,
    started_at: str,
    completed_at: str,
    status: str,
    runner_outcome: str,
    exit_code: int | None,
    stdout: bytes | str | None,
    stderr: bytes | str | None,
    stdout_complete: bool,
    stderr_complete: bool,
    workspace_porcelain_sha256_before: str,
    workspace_porcelain_sha256_after: str,
) -> dict[str, Any]:
    stdout_text, stdout_was_bounded = _bounded_utf8(stdout)
    stderr_text, stderr_was_bounded = _bounded_utf8(stderr)
    stdout_complete = stdout_complete and stdout_was_bounded
    stderr_complete = stderr_complete and stderr_was_bounded
    if status not in {"TIMEOUT", "INTERRUPTED", "RUNNER_ERROR"} and (
        not stdout_complete or not stderr_complete
    ):
        status = "OUTPUT_LIMIT_EXCEEDED"
        runner_outcome = "OUTPUT_LIMIT_EXCEEDED"
        stdout_complete = False
        stderr_complete = False
    receipt = build_v32_postcommit_regression_execution_receipt_v1(
        receipt_id=f"{reservation['qualification_run_id']}:{suite_id.lower()}:attempt-1",
        suite_id=suite_id,
        started_at=started_at,
        completed_at=completed_at,
        target_run_id=reservation["target_run_id"],
        qualification_run_id=reservation["qualification_run_id"],
        branch=reservation["branch"],
        frozen_commit_sha=reservation["frozen_commit_sha"],
        frozen_tree_sha=reservation["frozen_tree_sha"],
        python_executable=reservation["python_executable"],
        python_realpath=reservation["python_realpath"],
        python_physical_sha256=reservation["python_physical_sha256"],
        python_version=reservation["python_version"],
        cwd=reservation["cwd"],
        status=status,
        runner_outcome=runner_outcome,
        exit_code=exit_code,
        stdout_utf8=stdout_text,
        stderr_utf8=stderr_text,
        stdout_complete=stdout_complete,
        stderr_complete=stderr_complete,
        workspace_porcelain_sha256_before=workspace_porcelain_sha256_before,
        workspace_porcelain_sha256_after=workspace_porcelain_sha256_after,
    )
    secure_write_once_json(
        root,
        paths[f"receipt:{suite_id}"],
        receipt,
        digest_field=EXECUTION_DIGEST_FIELD,
        require_new=True,
    )
    return receipt


def run_v32_postcommit_regressions_once_v1(
    *,
    project_root: Path,
    target_run_id: str,
    qualification_run_id: str,
) -> Mapping[str, Any]:
    """Reject every attempt to create new run-scoped legacy double-suite receipts."""

    raise V32PostCommitRegressionInfrastructureError(
        "V32_POSTCOMMIT_LEGACY_WRITER_RETIRED"
    )


def _load_exact(
    root: Path,
    binding: Mapping[str, Any],
    *,
    schema_id: str,
    digest_field: str,
) -> dict[str, Any]:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_BINDING_INVALID"
        )
    try:
        document = secure_load_json_document(root, str(binding["path"]))
        recovered = secure_binding_for_existing_document(
            root, str(binding["path"]), digest_field=digest_field
        )
    except (OSError, TypeError, ValueError, V32SecureWriteOnceStoreError) as exc:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PHYSICAL_REPLAY_FAILED"
        ) from exc
    if (
        document.get("schema_id") != schema_id
        or recovered != dict(binding)
    ):
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_BINDING_INVALID"
        )
    return document


def _assert_exact_prequalification_tree(root: Path, paths: Mapping[str, str]) -> None:
    expected = {
        paths["reservation"],
        paths["aggregate"],
        *(paths[f"receipt:{suite_id}"] for suite_id in SUITE_IDS),
    }
    base = root / paths["root"]
    if base.is_symlink() or not base.is_dir():
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PREQUALIFICATION_TREE_INVALID"
        )
    observed: set[str] = set()
    for current, directories, files in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            child = current_path / name
            try:
                mode = os.lstat(child).st_mode
            except OSError as exc:
                raise V32PostCommitRegressionInfrastructureError(
                    "V32_POSTCOMMIT_PREQUALIFICATION_TREE_INVALID"
                ) from exc
            if stat.S_ISLNK(mode):
                raise V32PostCommitRegressionInfrastructureError(
                    "V32_POSTCOMMIT_PREQUALIFICATION_TREE_INVALID"
                )
        for name in files:
            observed.add((current_path / name).relative_to(root).as_posix())
    if observed != expected:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PREQUALIFICATION_TREE_INVALID"
        )


def load_v32_postcommit_regression_prequalification_support_v1(
    *, project_root: Path, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Reopen one successful prequalification namespace and plan exact copies."""

    root = _root(project_root)
    target, qualification = _ids(target_run_id, qualification_run_id)
    paths = prequalification_paths_v1(qualification)
    _assert_exact_prequalification_tree(root, paths)
    try:
        reservation = secure_load_json_document(root, paths["reservation"])
        verify_v32_postcommit_regression_reservation_v1(reservation)
        receipts = {
            suite_id: secure_load_json_document(root, paths[f"receipt:{suite_id}"])
            for suite_id in SUITE_IDS
        }
        for receipt in receipts.values():
            verify_v32_postcommit_regression_execution_receipt_v1(receipt)
        aggregate = secure_load_json_document(root, paths["aggregate"])
        verify_v32_postcommit_regression_aggregate_support_v1(
            aggregate,
            reservation=reservation,
            execution_receipts=receipts,
        )
    except (OSError, TypeError, ValueError, V32SecureWriteOnceStoreError) as exc:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PREQUALIFICATION_REPLAY_FAILED"
        ) from exc
    if reservation.get("target_run_id") != target or reservation.get("qualification_run_id") != qualification:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PREQUALIFICATION_IDENTITY_DRIFT"
        )
    identity = _git_identity(root)
    status_raw, artifacts, clean = _workspace_observation(root)
    executable, realpath, physical, version, python_exact = _python_identity()
    if (
        not clean
        or not python_exact
        or identity != {key: reservation[key] for key in identity}
        or artifacts != reservation["allowed_untracked_user_artifacts"]
        or hashlib.sha256(status_raw).hexdigest()
        != reservation["workspace_porcelain_sha256"]
        or executable != reservation["python_executable"]
        or realpath != reservation["python_realpath"]
        or physical != reservation["python_physical_sha256"]
        or version != reservation["python_version"]
        or root.as_posix() != reservation["cwd"]
    ):
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_WORKSPACE_OR_RUNTIME_DRIFT"
        )
    support_paths = qualification_support_paths_v1(qualification)
    planned_reservation_binding = _planned_binding(
        support_paths["reservation"], reservation, RESERVATION_DIGEST_FIELD
    )
    planned_receipt_bindings = {
        suite_id: _planned_binding(
            support_paths[f"receipt:{suite_id}"], receipts[suite_id], EXECUTION_DIGEST_FIELD
        )
        for suite_id in SUITE_IDS
    }
    if (
        aggregate["reservation_binding"] != planned_reservation_binding
        or aggregate["execution_receipt_bindings"] != planned_receipt_bindings
    ):
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_PLANNED_SUPPORT_BINDING_DRIFT"
        )
    aggregate_binding = _planned_binding(
        support_paths["aggregate"], aggregate, AGGREGATE_DIGEST_FIELD
    )
    return {
        "reservation": reservation,
        "execution_receipts": receipts,
        "aggregate": aggregate,
        "aggregate_binding": aggregate_binding,
        "support_artifacts": [
            (support_paths["reservation"], reservation, RESERVATION_DIGEST_FIELD),
            *(
                (support_paths[f"receipt:{suite_id}"], receipts[suite_id], EXECUTION_DIGEST_FIELD)
                for suite_id in SUITE_IDS
            ),
            (support_paths["aggregate"], aggregate, AGGREGATE_DIGEST_FIELD),
        ],
    }


def replay_v32_postcommit_regression_aggregate_support_v1(
    *,
    project_root: Path,
    aggregate_binding: Mapping[str, Any],
    expected_target_run_id: str | None = None,
    expected_qualification_run_id: str | None = None,
) -> Mapping[str, Any]:
    """Physically reopen aggregate, reservation, and both execution receipts."""

    root = _root(project_root)
    aggregate = _load_exact(
        root,
        aggregate_binding,
        schema_id=AGGREGATE_SCHEMA_ID,
        digest_field=AGGREGATE_DIGEST_FIELD,
    )
    qualification = str(aggregate.get("qualification_run_id"))
    support_paths = qualification_support_paths_v1(qualification)
    if aggregate_binding.get("path") != support_paths["aggregate"]:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_AGGREGATE_PATH_INVALID"
        )
    reservation = _load_exact(
        root,
        aggregate.get("reservation_binding"),
        schema_id=RESERVATION_SCHEMA_ID,
        digest_field=RESERVATION_DIGEST_FIELD,
    )
    receipts = {
        suite_id: _load_exact(
            root,
            aggregate.get("execution_receipt_bindings", {}).get(suite_id),
            schema_id=EXECUTION_SCHEMA_ID,
            digest_field=EXECUTION_DIGEST_FIELD,
        )
        for suite_id in SUITE_IDS
    }
    try:
        digest = verify_v32_postcommit_regression_aggregate_support_v1(
            aggregate,
            reservation=reservation,
            execution_receipts=receipts,
        )
    except V32PostCommitRegressionError as exc:
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_AGGREGATE_REPLAY_INVALID"
        ) from exc
    if (
        expected_target_run_id is not None
        and aggregate.get("target_run_id") != expected_target_run_id
    ) or (
        expected_qualification_run_id is not None
        and aggregate.get("qualification_run_id") != expected_qualification_run_id
    ):
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_AGGREGATE_IDENTITY_DRIFT"
        )
    identity = _git_identity(root)
    executable, realpath, physical, version, python_exact = _python_identity()
    if (
        identity != {key: aggregate[key] for key in identity}
        or root.as_posix() != aggregate["cwd"]
        or not python_exact
        or executable != aggregate["python_executable"]
        or realpath != aggregate["python_realpath"]
        or physical != aggregate["python_physical_sha256"]
        or version != aggregate["python_version"]
    ):
        raise V32PostCommitRegressionInfrastructureError(
            "V32_POSTCOMMIT_GIT_IDENTITY_DRIFT"
        )
    return {
        "aggregate_digest": digest,
        "aggregate": aggregate,
        "reservation": reservation,
        "execution_receipts": receipts,
        "full_physical_replay_verified": True,
        "network_calls": 0,
    }


__all__ = [
    "V32PostCommitRegressionInfrastructureError",
    "load_v32_postcommit_regression_prequalification_support_v1",
    "replay_v32_postcommit_regression_aggregate_support_v1",
]
