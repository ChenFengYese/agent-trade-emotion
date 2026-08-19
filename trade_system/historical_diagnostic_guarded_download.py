"""Narrow, receipt-bound transport for the S0-009 February archive gate.

This is deliberately separate from the diagnostic application.  It has no CLI,
no account credentials, and no model or trading imports.  A call is refused
until a future Sol addendum binds this source and the subordinate resource
policy.  The checked-in policy is intentionally only a HOLD draft.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Protocol

from .historical_diagnostic_authorization import (
    HistoricalDiagnosticAuthorizationError,
    canonical_sha256,
    sha256_file,
    verify_authorized_execution_contract,
    verify_pre_download_absence_inventory,
    verify_pre_download_authorization_receipt,
)


GUARD_POLICY_RECORD = "s0_009_subordinate_resource_guard.v1"
GUARDED_MANIFEST_RECORD = "s0_009_guarded_download_manifest.v1"
FINAL_ADDENDUM_RECORD = "sol_s0_009_subordinate_resource_addendum.v1"
OLD_RELEASE_STATE = "SUSPENDED_REQUIRES_RESOURCE_GUARD"
HOLD_STATE = "HOLD_AWAITING_FINAL_SOL_BINDING"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_CHECKSUM_BYTES = 8 * 1024
MIN_FREE_AFTER_BYTES = 8 * 1024 * 1024 * 1024
MIN_ARCHIVE_BUDGET_EACH = 4 * 1024 * 1024
OFFICIAL_HOST = "data.binance.vision"
CHUNK_BYTES = 64 * 1024
PARENT_RELEASE_PATH = ".runtime/historical-diagnostic-s0-009-release/release-report.v1.json"
PARENT_RELEASE_SHA256 = "35862a13f33a4e6456fa6e36e5c49b9abd143e1fbda242edc293cb2d74e24fa8"
SOL_R1_PATH = "config/sol_decision.s0-009-feb-falsification.v1.json"
SOL_R1_SHA256 = "d9e11df2e533266568b642409e15db566035f8126152a4b5c70992440d8210f3"
PARENT_INVENTORY_PATH = ".runtime/historical-diagnostic-s0-009-release/all-targets-absent-inventory.v1.json"
PARENT_INVENTORY_SHA256 = "85e86fcbbf4bfed60daa2bea04c11a266f0ed95531ed724c2a4ddad68e0c4049"
FINAL_ADDENDUM_ID = "SOL-S0-009-R1-RESOURCE-ATTENUATION-A1"


class GuardedDownloadError(HistoricalDiagnosticAuthorizationError):
    pass


class Response(Protocol):
    url: str
    headers: Mapping[str, str]

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


Transport = Callable[[str], Response]
FreeBytes = Callable[[Path], int]
Fsync = Callable[[int], None]


def _load(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardedDownloadError("cannot load %s" % label) from exc
    if not isinstance(value, dict):
        raise GuardedDownloadError("%s must be an object" % label)
    return value


def _relative(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise GuardedDownloadError("%s is required" % field)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise GuardedDownloadError("%s must be workspace-relative" % field)
    return root / path


def _source_binding(root: Path, binding: Any, field: str) -> Dict[str, str]:
    if not isinstance(binding, dict):
        raise GuardedDownloadError("%s binding is required" % field)
    path = _relative(root, binding.get("path"), field + ".path")
    digest = binding.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or not path.is_file() or sha256_file(path) != digest:
        raise GuardedDownloadError("%s binding drifted" % field)
    return {"path": binding["path"], "sha256": digest}


def _file_binding(root: Path, binding: Any, field: str) -> Dict[str, str]:
    if not isinstance(binding, dict):
        raise GuardedDownloadError("%s binding is required" % field)
    path = _relative(root, binding.get("path"), field + ".path")
    digest = binding.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or not path.is_file() or sha256_file(path) != digest:
        raise GuardedDownloadError("%s binding drifted" % field)
    return {"path": binding["path"], "sha256": digest}


def _exact_file_binding(root: Path, binding: Any, *, path: str, sha256: str, field: str) -> None:
    if not isinstance(binding, dict) or binding.get("path") != path or binding.get("sha256") != sha256:
        raise GuardedDownloadError("%s does not bind the exact parent artifact" % field)
    resolved = _relative(root, path, field + ".path")
    if not resolved.is_file() or sha256_file(resolved) != sha256:
        raise GuardedDownloadError("%s parent artifact drifted" % field)


def _receipt_scope(receipt: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in receipt.items() if key not in {"authorized_execution_contract", "receipt_scope_sha256"}})


def _limits(policy: Mapping[str, Any], receipt: Mapping[str, Any]) -> Dict[str, int]:
    limits = policy.get("resource_limits")
    if not isinstance(limits, dict):
        raise GuardedDownloadError("resource limits are required")
    expected = {
        "max_archive_bytes_each": MAX_ARCHIVE_BYTES,
        "max_total_archive_bytes": MAX_TOTAL_ARCHIVE_BYTES,
        "max_checksum_bytes_each": MAX_CHECKSUM_BYTES,
        "minimum_free_bytes_after_maximum_download": MIN_FREE_AFTER_BYTES,
        "minimum_archive_budget_each": MIN_ARCHIVE_BUDGET_EACH,
    }
    if limits != expected:
        raise GuardedDownloadError("subordinate resource limits are not the fixed narrow values")
    parent = receipt.get("download_limits")
    if not isinstance(parent, dict) or not all(isinstance(parent.get(key), int) and parent[key] > 0 for key in ("max_archive_bytes_each", "max_total_archive_bytes")):
        raise GuardedDownloadError("parent receipt download limits are invalid")
    effective = {
        "max_archive_bytes_each": min(parent["max_archive_bytes_each"], MAX_ARCHIVE_BYTES),
        "max_total_archive_bytes": min(parent["max_total_archive_bytes"], MAX_TOTAL_ARCHIVE_BYTES),
        "max_checksum_bytes_each": MAX_CHECKSUM_BYTES,
        "minimum_free_bytes_after_maximum_download": MIN_FREE_AFTER_BYTES,
    }
    if effective["max_archive_bytes_each"] != MAX_ARCHIVE_BYTES or effective["max_total_archive_bytes"] != MAX_TOTAL_ARCHIVE_BYTES:
        raise GuardedDownloadError("effective limits are not the policy minimum of parent and guard")
    if effective["max_total_archive_bytes"] < 84 * MIN_ARCHIVE_BUDGET_EACH:
        raise GuardedDownloadError("total archive limit lacks a reasonable 84-target budget")
    return effective


def _binding_matches(binding: Any, expected: Mapping[str, Any], field: str) -> None:
    if not isinstance(binding, dict) or any(binding.get(key) != value for key, value in expected.items()):
        raise GuardedDownloadError("%s binding drifted" % field)


def verify_guarded_download_authority(
    *,
    policy_path: Path,
    addendum_path: Path,
    receipt_path: Path,
    contract_path: Path,
    plan_path: Path,
    workspace_root: Path,
    require_current_absence: bool = True,
) -> Dict[str, Any]:
    """Require the one parent receipt plus a later exact Sol guard addendum.

    The repository does not ship such a final addendum.  Keeping this verifier
    strict makes the checked-in subordinate package a HOLD, not latent download
    permission.
    """
    root = Path(workspace_root).resolve()
    receipt = _load(receipt_path, "parent authorization receipt")
    try:
        parent = verify_pre_download_authorization_receipt(receipt_path, plan_path=plan_path, workspace_root=root)
        contract = verify_authorized_execution_contract(contract_path, receipt_path, plan_path=plan_path, workspace_root=root)
    except HistoricalDiagnosticAuthorizationError as exc:
        raise GuardedDownloadError("parent receipt or contract is not verifiable") from exc
    policy = _load(policy_path, "subordinate resource policy")
    if policy.get("record_type") != GUARD_POLICY_RECORD or policy.get("status") != HOLD_STATE:
        raise GuardedDownloadError("resource policy is not an awaiting-Sol HOLD")
    if policy.get("parent_release_state") != OLD_RELEASE_STATE:
        raise GuardedDownloadError("parent release is not explicitly suspended pending resource guard")
    _exact_file_binding(root, policy.get("parent_release"), path=PARENT_RELEASE_PATH, sha256=PARENT_RELEASE_SHA256, field="policy parent release")
    _exact_file_binding(root, policy.get("sol_r1"), path=SOL_R1_PATH, sha256=SOL_R1_SHA256, field="policy Sol R1")
    _exact_file_binding(root, policy.get("parent_inventory"), path=PARENT_INVENTORY_PATH, sha256=PARENT_INVENTORY_SHA256, field="policy original absence inventory")
    current_inventory_binding = _file_binding(root, policy.get("current_absence_revalidation"), "policy current absence revalidation")
    current_inventory = _load(_relative(root, current_inventory_binding["path"], "policy current absence revalidation.path"), "current absence revalidation")
    try:
        verify_pre_download_absence_inventory(current_inventory, plan_path=plan_path, workspace_root=root, require_current_absence=require_current_absence)
    except HistoricalDiagnosticAuthorizationError as exc:
        raise GuardedDownloadError("current absence revalidation no longer holds") from exc
    expected_parent = {
        "receipt_id": receipt.get("receipt_id"),
        "receipt_scope_sha256": _receipt_scope(receipt),
        "receipt_sha256": sha256_file(receipt_path),
        "contract_sha256": sha256_file(contract_path),
    }
    _binding_matches(policy.get("parent_authorization"), expected_parent, "policy parent authorization")
    downloader = _source_binding(root, policy.get("guarded_downloader"), "policy guarded downloader")
    effective = _limits(policy, receipt)
    addendum = _load(addendum_path, "final Sol subordinate addendum")
    if addendum.get("record_type") != FINAL_ADDENDUM_RECORD or addendum.get("status") != "FINAL_SOL_BOUND_RESOURCE_GUARD" or addendum.get("addendum_id") != FINAL_ADDENDUM_ID:
        raise GuardedDownloadError("final Sol subordinate addendum is absent or not final")
    _binding_matches(addendum.get("parent_authorization"), expected_parent, "addendum parent authorization")
    _binding_matches(addendum.get("resource_policy"), {"path": str(Path(policy_path).resolve().relative_to(root)), "sha256": sha256_file(policy_path)}, "addendum resource policy")
    _binding_matches(addendum.get("guarded_downloader"), downloader, "addendum guarded downloader")
    package_binding = _file_binding(root, addendum.get("source_package"), "addendum source package")
    test_binding = _file_binding(root, addendum.get("test_report"), "addendum test report")
    package = _load(_relative(root, package_binding["path"], "addendum source package.path"), "guarded source package")
    test_report = _load(_relative(root, test_binding["path"], "addendum test report.path"), "guarded test report")
    if package.get("policy") != {"path": str(Path(policy_path).resolve().relative_to(root)), "sha256": sha256_file(policy_path)} or package.get("guarded_downloader") != downloader:
        raise GuardedDownloadError("source package does not bind exact policy and downloader")
    if test_report.get("policy") != {"path": str(Path(policy_path).resolve().relative_to(root)), "sha256": sha256_file(policy_path)} or test_report.get("source_package") != package_binding:
        raise GuardedDownloadError("test report does not bind exact policy and source package")
    if addendum.get("authorization_receipt_limit") != 1 or addendum.get("new_authorization_receipt") is not False:
        raise GuardedDownloadError("addendum must retain the single parent receipt without minting another")
    if addendum.get("eligible_for_binance_g2") is not False or addendum.get("trading_authorization") != "DENIED":
        raise GuardedDownloadError("guarded authority cannot grant G2 or trading")
    return {
        "record_type": "s0_009_guarded_download_authority_verification.v1",
        "verified": True,
        "receipt_id": parent["receipt_id"],
        "contract_id": contract["contract_id"],
        "addendum_id": addendum["addendum_id"],
        "addendum_sha256": sha256_file(addendum_path),
        "guarded_downloader": downloader,
        "transport_mode": "OFFICIAL_NETWORK_ONLY",
        "effective_limits": effective,
        "status": "FINAL_SOL_BOUND_RESOURCE_GUARD",
        "eligible_for_binance_g2": False,
        "trading_authorization": "DENIED",
    }


def _exact_official_url(url: str, expected: str) -> None:
    if url != expected:
        raise GuardedDownloadError("download URL is not the exact receipt target")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
        raise GuardedDownloadError("download URL is not exact HTTPS data.binance.vision")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _network_transport(expected_url: str) -> Response:
    # This is never reached by the checked-in HOLD policy because final Sol
    # addendum verification fails first.  It remains deliberately minimal.
    _exact_official_url(expected_url, expected_url)
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(expected_url, headers={"User-Agent": "s0-009-guarded-diagnostic/1"})
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.URLError as exc:
        raise GuardedDownloadError("official target request failed") from exc
    return response  # type: ignore[return-value]


def _content_length(response: Response) -> int | None:
    raw = response.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise GuardedDownloadError("Content-Length is invalid") from exc
    if value < 0:
        raise GuardedDownloadError("Content-Length is negative")
    return value


def _safe_target(root: Path, relative: str) -> Path:
    target = _relative(root, relative, "target path")
    # Existing symlink parents would invalidate the no-overwrite boundary.
    parent = target.parent
    while parent != root:
        if parent.exists() and parent.is_symlink():
            raise GuardedDownloadError("target parent symlink is refused")
        parent = parent.parent
    return target


def _temporary_path(target: Path) -> Path:
    return target.with_name(target.name + ".partial")


def _preflight_targets(root: Path, targets: list[Mapping[str, Any]]) -> None:
    for target in targets:
        for field in ("archive_path", "checksum_path"):
            final = _safe_target(root, str(target[field]))
            temporary = _temporary_path(final)
            if final.exists() or final.is_symlink() or temporary.exists() or temporary.is_symlink():
                raise GuardedDownloadError("existing final or temporary target refuses a guarded run")


def _open_secure_parent(root: Path, relative_parent: Path, *, fsync: Fsync = os.fsync) -> int:
    """Open/create a directory chain without following symlinks.

    The returned fd pins the directory object.  A rename after opening can at
    worst leave an unpublished file in the old directory; it cannot redirect a
    write outside the workspace.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, flags)
    current = root_fd
    try:
        for part in relative_parent.parts:
            if part in ("", "."):
                continue
            try:
                os.mkdir(part, 0o700, dir_fd=current)
                fsync(current)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _publish_no_overwrite_at(parent_fd: int, temporary_name: str, final_name: str, *, fsync: Fsync) -> None:
    # link then unlink is no-overwrite and crash-safe: final is durable before
    # the temporary name is retired.  A crash can only leave a .partial, which
    # a later guarded attempt deliberately refuses.
    os.link(temporary_name, final_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
    fsync(parent_fd)
    os.unlink(temporary_name, dir_fd=parent_fd)
    fsync(parent_fd)


def _stream_to_temp_at(
    *,
    url: str,
    expected_url: str,
    parent_fd: int,
    temporary_name: str,
    final_name: str,
    publish_path: str,
    per_file_limit: int,
    remaining_total: int,
    transport: Transport,
    fsync: Fsync,
    publish: Callable[[int, str, str], None] | None,
) -> Dict[str, Any]:
    _exact_official_url(url, expected_url)
    # Reserve the exact temporary name before opening any network connection.
    # This closes the preflight-to-open race: an existing .partial is rejected
    # with zero transport/body activity.
    descriptor = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
    fsync(parent_fd)
    response: Response | None = None
    try:
        response = transport(url)
        if getattr(response, "url", None) != url:
            raise GuardedDownloadError("redirect or response URL drift is refused")
        length = _content_length(response)
        if length is not None and (length > per_file_limit or length > remaining_total):
            raise GuardedDownloadError("Content-Length exceeds guarded resource limit")
        total = 0
        digest = hashlib.sha256()
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        with handle:
            while True:
                block = response.read(CHUNK_BYTES)
                if not block:
                    break
                if not isinstance(block, bytes):
                    raise GuardedDownloadError("transport returned a non-bytes body")
                total += len(block)
                if total > per_file_limit or total > remaining_total:
                    raise GuardedDownloadError("streamed body exceeds guarded resource limit")
                digest.update(block)
                handle.write(block)
            handle.flush(); fsync(handle.fileno())
        fsync(parent_fd)
        if publish is not None:
            publish(parent_fd, temporary_name, final_name)
        return {"actual_bytes": total, "content_length": length, "sha256": digest.hexdigest(), "publish_path": publish_path}
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if response is not None:
            response.close()


def _checksum_token_at(parent_fd: int, filename: str, expected_filename: str) -> str:
    descriptor = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        raw = os.read(descriptor, MAX_CHECKSUM_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_CHECKSUM_BYTES:
        raise GuardedDownloadError("official checksum exceeds guarded byte limit")
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise GuardedDownloadError("official checksum cannot be read as ASCII") from exc
    tokens = text.split()
    if len(tokens) != 2 or tokens[1] != expected_filename or len(tokens[0]) != 64 or any(char not in "0123456789abcdefABCDEF" for char in tokens[0]):
        raise GuardedDownloadError("official checksum declaration is invalid")
    return tokens[0].lower()


def _write_once_json(path: Path, value: Mapping[str, Any], *, root: Path | None = None, fsync: Fsync = os.fsync) -> str:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if root is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
    else:
        relative = path.relative_to(root)
        parent_fd = _open_secure_parent(root, relative.parent, fsync=fsync)
        try:
            descriptor = os.open(relative.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded); handle.flush(); fsync(handle.fileno())
            fsync(parent_fd)
        except FileExistsError as exc:
            raise GuardedDownloadError("guarded download manifest already exists") from exc
        finally:
            os.close(parent_fd)
        return hashlib.sha256(encoded).hexdigest()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise GuardedDownloadError("guarded download manifest already exists") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded); handle.flush(); fsync(handle.fileno())
    return hashlib.sha256(encoded).hexdigest()


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _run_guarded_download_core(
    *,
    policy_path: Path,
    final_addendum_path: Path,
    receipt_path: Path,
    contract_path: Path,
    plan_path: Path,
    workspace_root: Path,
    manifest_path: Path,
    transport: Transport | None = None,
    publisher: Callable[[int, str, str], None] | None = None,
    free_bytes: FreeBytes = _free_bytes,
    fsync: Fsync = os.fsync,
    transport_mode: str,
) -> Dict[str, Any]:
    """Download only the exact parent 84 archive/checksum pairs under the guard.

    A failure writes a factual failed manifest (when authority was established)
    and leaves any partial body in place, which makes a second run fail closed.
    """
    root = Path(workspace_root).resolve()
    if transport_mode == "OFFICIAL_NETWORK_ONLY" and (transport is not _network_transport or publisher is not None or free_bytes is not _free_bytes or fsync is not os.fsync):
        raise GuardedDownloadError("official transport mode refuses test overrides")
    if transport_mode not in {"OFFICIAL_NETWORK_ONLY", "TEST_ONLY_FAKE_TRANSPORT"}:
        raise GuardedDownloadError("guarded transport mode is invalid")
    manifest = _relative(root, str(manifest_path), "manifest path")
    if manifest.exists() or manifest.is_symlink():
        raise GuardedDownloadError("guarded download manifest already exists")
    authority = verify_guarded_download_authority(
        policy_path=policy_path, addendum_path=final_addendum_path, receipt_path=receipt_path,
        contract_path=contract_path, plan_path=plan_path, workspace_root=root,
    )
    receipt = _load(receipt_path, "parent authorization receipt")
    inventory = receipt["absence_inventory"]
    targets = receipt["authorized_targets"]
    effective = authority["effective_limits"]
    target_records: list[Dict[str, Any]] = []
    total_archives = 0
    temporary_paths: list[str] = []
    published_paths: list[str] = []
    disk_gate_checks: list[Dict[str, int]] = []
    try:
        try:
            verify_pre_download_absence_inventory(inventory, plan_path=plan_path, workspace_root=root, require_current_absence=True)
        except HistoricalDiagnosticAuthorizationError as exc:
            raise GuardedDownloadError("current absence gate refused the guarded run") from exc
        if not isinstance(targets, list) or len(targets) != 84:
            raise GuardedDownloadError("parent receipt lacks exactly 84 targets")
        _preflight_targets(root, targets)
        initial_remaining = effective["max_total_archive_bytes"] + len(targets) * effective["max_checksum_bytes_each"]
        available = free_bytes(root)
        disk_gate_checks.append({"free_bytes": available, "remaining_archive_bytes": effective["max_total_archive_bytes"], "remaining_checksum_bytes": len(targets) * effective["max_checksum_bytes_each"], "remaining_max_download_bytes": initial_remaining, "formula": "remaining_archives_plus_remaining_checksums"})
        if not isinstance(available, int) or available - initial_remaining < effective["minimum_free_bytes_after_maximum_download"]:
            raise GuardedDownloadError("disk gate refuses before any response body is read")
        use_transport = transport or _network_transport
        publish = publisher or (lambda parent_fd, temporary_name, final_name: _publish_no_overwrite_at(parent_fd, temporary_name, final_name, fsync=fsync))
        for target in targets if isinstance(targets, list) else []:
            remaining_archive_bytes = effective["max_total_archive_bytes"] - total_archives
            remaining_checksum_bytes = (len(targets) - len(target_records)) * effective["max_checksum_bytes_each"]
            remaining_max_download_bytes = remaining_archive_bytes + remaining_checksum_bytes
            available = free_bytes(root)
            disk_gate_checks.append({"free_bytes": available, "remaining_archive_bytes": remaining_archive_bytes, "remaining_checksum_bytes": remaining_checksum_bytes, "remaining_max_download_bytes": remaining_max_download_bytes, "formula": "remaining_archives_plus_remaining_checksums"})
            if not isinstance(available, int) or available - remaining_max_download_bytes < effective["minimum_free_bytes_after_maximum_download"]:
                raise GuardedDownloadError("disk gate refuses before this archive transport/body")
            archive_relative = Path(target["archive_path"])
            checksum_relative = Path(target["checksum_path"])
            if archive_relative.parent != checksum_relative.parent:
                raise GuardedDownloadError("archive and checksum parent directories differ")
            parent_fd = _open_secure_parent(root, archive_relative.parent, fsync=fsync)
            try:
                checksum_result = _stream_to_temp_at(
                    url=target["checksum_url"], expected_url=target["checksum_url"], parent_fd=parent_fd,
                    temporary_name=checksum_relative.name + ".partial", final_name=checksum_relative.name, publish_path=str(checksum_relative),
                    per_file_limit=effective["max_checksum_bytes_each"], remaining_total=effective["max_checksum_bytes_each"],
                    transport=use_transport, fsync=fsync, publish=publish,
                )
                published_paths.append(str(checksum_relative))
                expected_sha = _checksum_token_at(parent_fd, checksum_relative.name, archive_relative.name)
                archive_result = _stream_to_temp_at(
                    url=target["archive_url"], expected_url=target["archive_url"], parent_fd=parent_fd,
                    temporary_name=archive_relative.name + ".partial", final_name=archive_relative.name, publish_path=str(archive_relative),
                    per_file_limit=effective["max_archive_bytes_each"], remaining_total=effective["max_total_archive_bytes"] - total_archives,
                    transport=use_transport, fsync=fsync, publish=None,
                )
                if archive_result["sha256"] != expected_sha:
                    raise GuardedDownloadError("archive SHA-256 differs from the official checksum")
                # Archive bodies stay as durable partials until their official
                # checksum is parsed and matches; a mismatch never publishes a
                # final archive name.
                publish(parent_fd, archive_relative.name + ".partial", archive_relative.name)
                published_paths.append(str(archive_relative))
                total_archives += archive_result["actual_bytes"]
                target_records.append({
                    "kind": target["kind"], "date": target["date"], "archive_url": target["archive_url"], "checksum_url": target["checksum_url"],
                    "archive": archive_result, "official_checksum": expected_sha,
                    "checksum": dict(checksum_result, official_checksum_file_sha256=checksum_result["sha256"]),
                })
            finally:
                os.close(parent_fd)
        if len(target_records) != 84 or total_archives > effective["max_total_archive_bytes"]:
            raise GuardedDownloadError("guarded target count or aggregate size drifted")
        result: Dict[str, Any] = {
            "record_type": GUARDED_MANIFEST_RECORD, "status": "ACQUIRED_GUARDED_NOT_SCORED", "authority": authority,
            "parent_authorization": {"receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"]},
            "archive_count": 84, "checksum_count": 84, "total_archive_bytes": total_archives, "targets": target_records,
            "transport_mode": transport_mode, "disk_gate_checks": disk_gate_checks, "no_extra_targets": True, "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
        }
    except Exception as exc:
        for target in targets if isinstance(targets, list) else []:
            for field in ("archive_path", "checksum_path"):
                # Failure reporting must never recurse through a potentially
                # swapped parent directory.  This only records a lexical
                # workspace-relative candidate; it does not open or write it.
                candidate = root / (str(target[field]) + ".partial")
                if candidate.exists():
                    temporary_paths.append(str(candidate.relative_to(root)))
        result = {
            "record_type": GUARDED_MANIFEST_RECORD, "status": "FAILED_NOT_ACQUIRED", "authority": authority,
            "parent_authorization": {"receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"]},
            "failure_type": type(exc).__name__, "failure_message": str(exc), "published_paths": published_paths,
            "temporary_paths": temporary_paths, "transport_mode": transport_mode, "disk_gate_checks": disk_gate_checks, "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
        }
        _write_once_json(manifest, result, root=root, fsync=fsync)
        if isinstance(exc, GuardedDownloadError):
            raise
        raise GuardedDownloadError("guarded download failed") from exc
    _write_once_json(manifest, result, root=root, fsync=fsync)
    return result


def _run_guarded_download_test_only(
    *, policy_path: Path, final_addendum_path: Path, receipt_path: Path, contract_path: Path,
    plan_path: Path, workspace_root: Path, manifest_path: Path, transport: Transport,
    publisher: Callable[[int, str, str], None] | None = None, free_bytes: FreeBytes = _free_bytes,
    fsync: Fsync = os.fsync,
) -> Dict[str, Any]:
    """Test-only fake-transport path; its manifest cannot pass production verification."""
    return _run_guarded_download_core(
        policy_path=policy_path, final_addendum_path=final_addendum_path, receipt_path=receipt_path,
        contract_path=contract_path, plan_path=plan_path, workspace_root=workspace_root,
        manifest_path=manifest_path, transport=transport, publisher=publisher, free_bytes=free_bytes,
        fsync=fsync, transport_mode="TEST_ONLY_FAKE_TRANSPORT",
    )


def run_guarded_download(
    *,
    policy_path: Path,
    final_addendum_path: Path,
    receipt_path: Path,
    contract_path: Path,
    plan_path: Path,
    workspace_root: Path,
    manifest_path: Path,
) -> Dict[str, Any]:
    """The only production entrypoint: fixed official transport and OS gates."""
    return _run_guarded_download_core(
        policy_path=policy_path, final_addendum_path=final_addendum_path, receipt_path=receipt_path,
        contract_path=contract_path, plan_path=plan_path, workspace_root=workspace_root,
        manifest_path=manifest_path, transport=_network_transport, publisher=None,
        free_bytes=_free_bytes, fsync=os.fsync, transport_mode="OFFICIAL_NETWORK_ONLY",
    )


def _verify_guarded_acquisition_manifest(
    *,
    manifest_path: Path,
    policy_path: Path,
    final_addendum_path: Path,
    receipt_path: Path,
    contract_path: Path,
    plan_path: Path,
    workspace_root: Path,
    allow_test_only: bool,
) -> Dict[str, Any]:
    """Cross-validate a successful guarded manifest against the 84 files."""
    root = Path(workspace_root).resolve()
    authority = verify_guarded_download_authority(
        policy_path=policy_path, addendum_path=final_addendum_path, receipt_path=receipt_path,
        contract_path=contract_path, plan_path=plan_path, workspace_root=root, require_current_absence=False,
    )
    receipt = _load(receipt_path, "parent authorization receipt")
    value = _load(manifest_path, "guarded download manifest")
    if value.get("record_type") != GUARDED_MANIFEST_RECORD or value.get("status") != "ACQUIRED_GUARDED_NOT_SCORED":
        raise GuardedDownloadError("guarded manifest is not a successful unscored acquisition")
    if value.get("transport_mode") != "OFFICIAL_NETWORK_ONLY" and not (allow_test_only and value.get("transport_mode") == "TEST_ONLY_FAKE_TRANSPORT"):
        raise GuardedDownloadError("production guarded acquisition verifier refuses a non-official transport manifest")
    if value.get("authority") != authority or value.get("parent_authorization") != {"receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"]}:
        raise GuardedDownloadError("guarded manifest authority binding drifted")
    records = value.get("targets")
    if not isinstance(records, list) or len(records) != 84 or value.get("archive_count") != 84 or value.get("checksum_count") != 84:
        raise GuardedDownloadError("guarded manifest lacks exactly 84 archive/checksum records")
    expected = {(item["kind"], item["date"]): item for item in receipt["authorized_targets"]}
    total = 0
    observed_paths: set[str] = set()
    for item in records:
        key = (item.get("kind"), item.get("date"))
        target = expected.pop(key, None)
        if target is None or item.get("archive_url") != target["archive_url"] or item.get("checksum_url") != target["checksum_url"]:
            raise GuardedDownloadError("guarded manifest target URL drifted")
        archive = _safe_target(root, target["archive_path"]); checksum = _safe_target(root, target["checksum_path"])
        if not archive.is_file() or not checksum.is_file() or archive.is_symlink() or checksum.is_symlink() or _temporary_path(archive).exists() or _temporary_path(checksum).exists():
            raise GuardedDownloadError("guarded target file is missing or partial remains")
        archive_record, checksum_record = item.get("archive"), item.get("checksum")
        if not isinstance(archive_record, dict) or not isinstance(checksum_record, dict):
            raise GuardedDownloadError("guarded target records are invalid")
        if archive_record.get("publish_path") != target["archive_path"] or checksum_record.get("publish_path") != target["checksum_path"]:
            raise GuardedDownloadError("guarded published path drifted")
        if sha256_file(archive) != archive_record.get("sha256") or sha256_file(checksum) != checksum_record.get("official_checksum_file_sha256"):
            raise GuardedDownloadError("guarded target digest drifted")
        if archive.stat().st_size != archive_record.get("actual_bytes") or checksum.stat().st_size != checksum_record.get("actual_bytes"):
            raise GuardedDownloadError("guarded target byte count drifted")
        if archive.stat().st_size > authority["effective_limits"]["max_archive_bytes_each"] or checksum.stat().st_size > authority["effective_limits"]["max_checksum_bytes_each"]:
            raise GuardedDownloadError("guarded target exceeds effective limits")
        parent_fd = _open_secure_parent(root, Path(target["archive_path"]).parent)
        try:
            official_checksum = _checksum_token_at(parent_fd, Path(target["checksum_path"]).name, archive.name)
        finally:
            os.close(parent_fd)
        if official_checksum != archive_record.get("sha256") or item.get("official_checksum") != archive_record.get("sha256"):
            raise GuardedDownloadError("guarded official checksum cross-validation failed")
        total += archive.stat().st_size
        observed_paths.update({str(archive.relative_to(root)), str(checksum.relative_to(root))})
    if expected or total != value.get("total_archive_bytes") or total > authority["effective_limits"]["max_total_archive_bytes"]:
        raise GuardedDownloadError("guarded aggregate archive evidence drifted")
    download_root = _relative(root, receipt["absence_inventory"]["download_root"], "download root")
    actual_paths = {str(path.relative_to(root)) for path in download_root.rglob("*") if path.is_file()}
    if actual_paths != observed_paths:
        raise GuardedDownloadError("guarded download root contains missing or extra files")
    return {"record_type": "s0_009_guarded_acquisition_verification.v1", "verified": True, "archive_count": 84, "checksum_count": 84, "total_archive_bytes": total, "status": "ACQUIRED_GUARDED_NOT_SCORED", "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}


def verify_guarded_acquisition_manifest(
    *, manifest_path: Path, policy_path: Path, final_addendum_path: Path, receipt_path: Path,
    contract_path: Path, plan_path: Path, workspace_root: Path,
) -> Dict[str, Any]:
    return _verify_guarded_acquisition_manifest(
        manifest_path=manifest_path, policy_path=policy_path, final_addendum_path=final_addendum_path,
        receipt_path=receipt_path, contract_path=contract_path, plan_path=plan_path,
        workspace_root=workspace_root, allow_test_only=False,
    )


def _verify_guarded_acquisition_manifest_test_only(**kwargs: Any) -> Dict[str, Any]:
    return _verify_guarded_acquisition_manifest(**kwargs, allow_test_only=True)
