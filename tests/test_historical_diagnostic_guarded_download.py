import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from trade_system.historical_diagnostic_authorization import build_pre_download_absence_inventory, sha256_file
from trade_system.historical_diagnostic_guarded_download import (
    FINAL_ADDENDUM_RECORD,
    GUARD_POLICY_RECORD,
    HOLD_STATE,
    MAX_ARCHIVE_BYTES,
    MAX_CHECKSUM_BYTES,
    MAX_TOTAL_ARCHIVE_BYTES,
    MIN_ARCHIVE_BUDGET_EACH,
    MIN_FREE_AFTER_BYTES,
    OLD_RELEASE_STATE,
    GuardedDownloadError,
    _open_secure_parent,
    _stream_to_temp_at,
    _run_guarded_download_test_only,
    _verify_guarded_acquisition_manifest_test_only,
    verify_guarded_acquisition_manifest,
    verify_guarded_download_authority,
)


PROJECT = Path(__file__).resolve().parents[1]
RELEASE = ".runtime/historical-diagnostic-s0-009-release"
PLAN = "config/binance_cm_historical_diagnostic.v2.frozen_before_download.json"
RECEIPT = RELEASE + "/authorization-receipt.v1.json"
CONTRACT = RELEASE + "/authorized-execution-contract.v2.json"


class FakeResponse:
    def __init__(self, body, *, content_length=None, url=None):
        self._body = body
        self._offset = 0
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}
        self.url = url
        self.read_count = 0
        self.closed = False

    def read(self, size=-1):
        self.read_count += 1
        if self._offset >= len(self._body):
            return b""
        if size < 0:
            size = len(self._body) - self._offset
        value = self._body[self._offset:self._offset + size]
        self._offset += len(value)
        return value

    def close(self):
        self.closed = True


class GuardedDownloadTests(unittest.TestCase):
    def setUp(self):
        # This suite exercises the pre-terminal guarded-download mechanics
        # against a copied February authority package.  The production
        # terminal-SEEN guard is covered separately and must remain active.
        # Patch only the authorization module's imported symbol so this
        # explicitly test-only fake-transport fixture can reach those mechanics.
        self.legacy_authority = patch(
            "trade_system.historical_diagnostic_authorization.reject_if_bound_february_terminal_identity",
            return_value=None,
        )
        self.legacy_authority.start()
        self.addCleanup(self.legacy_authority.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        for relative in (PLAN, "config/binance_cm_historical_evidence_ledger.v1.json", "config/sol_decision.s0-009-feb-falsification.v1.json"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, target)
        (self.root / ".runtime").mkdir(exist_ok=True)
        shutil.copytree(PROJECT / RELEASE, self.root / RELEASE)
        target = self.root / ".runtime/historical-experiments"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(PROJECT / ".runtime/historical-experiments", target_is_directory=True)
        (self.root / "trade_system").mkdir()
        for source in (
            "trade_system/historical_diagnostic_guarded_download.py",
            "trade_system/historical_diagnostic_application.py",
            "trade_system/historical_diagnostic_development.py",
        ):
            (self.root / source).symlink_to(PROJECT / source)
        self.receipt_path = self.root / RECEIPT
        self.contract_path = self.root / CONTRACT
        self.plan_path = self.root / PLAN
        self.policy_path = self.root / "evidence/policy.v1.json"
        self.current_inventory_path = self.root / "evidence/current-absence.v1.json"
        self.package_path = self.root / "evidence/source-package.v1.json"
        self.test_report_path = self.root / "evidence/test-report.v1.json"
        self.addendum_path = self.root / "evidence/final-addendum.v1.json"
        self.manifest_path = Path("evidence/guarded-manifest.v1.json")
        self._write_policy_and_addendum()

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    def _parent_authorization(self):
        receipt = json.loads(self.receipt_path.read_text())
        return {
            "receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"],
            "receipt_sha256": sha256_file(self.receipt_path), "contract_sha256": sha256_file(self.contract_path),
        }

    def _write_policy_and_addendum(self):
        source = "trade_system/historical_diagnostic_guarded_download.py"
        binding = {"path": source, "sha256": sha256_file(self.root / source)}
        policy = {
            "record_type": GUARD_POLICY_RECORD, "policy_id": "fixture-resource-guard", "status": HOLD_STATE,
            "parent_release_state": OLD_RELEASE_STATE,
            "parent_release": {"path": RELEASE + "/release-report.v1.json", "sha256": sha256_file(self.root / (RELEASE + "/release-report.v1.json"))},
            "sol_r1": {"path": "config/sol_decision.s0-009-feb-falsification.v1.json", "sha256": sha256_file(self.root / "config/sol_decision.s0-009-feb-falsification.v1.json")},
            "parent_inventory": {"path": RELEASE + "/all-targets-absent-inventory.v1.json", "sha256": sha256_file(self.root / (RELEASE + "/all-targets-absent-inventory.v1.json"))},
            "parent_authorization": self._parent_authorization(), "guarded_downloader": binding,
            "resource_limits": {"max_archive_bytes_each": MAX_ARCHIVE_BYTES, "max_total_archive_bytes": MAX_TOTAL_ARCHIVE_BYTES, "max_checksum_bytes_each": MAX_CHECKSUM_BYTES, "minimum_free_bytes_after_maximum_download": MIN_FREE_AFTER_BYTES, "minimum_archive_budget_each": MIN_ARCHIVE_BUDGET_EACH},
            "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
        }
        current = build_pre_download_absence_inventory(self.plan_path, workspace_root=self.root, download_root=json.loads(self.receipt_path.read_text())["absence_inventory"]["download_root"])
        self._write(self.current_inventory_path, current)
        policy["current_absence_revalidation"] = {"path": "evidence/current-absence.v1.json", "sha256": sha256_file(self.current_inventory_path)}
        self._write(self.policy_path, policy)
        policy_binding = {"path": "evidence/policy.v1.json", "sha256": sha256_file(self.policy_path)}
        package = {"record_type": "fixture-source-package", "policy": policy_binding, "guarded_downloader": binding}
        self._write(self.package_path, package)
        package_binding = {"path": "evidence/source-package.v1.json", "sha256": sha256_file(self.package_path)}
        test_report = {"record_type": "fixture-test-report", "policy": policy_binding, "source_package": package_binding}
        self._write(self.test_report_path, test_report)
        addendum = {
            "record_type": FINAL_ADDENDUM_RECORD, "addendum_id": "SOL-S0-009-R1-RESOURCE-ATTENUATION-A1", "status": "FINAL_SOL_BOUND_RESOURCE_GUARD",
            "parent_authorization": self._parent_authorization(), "resource_policy": {"path": "evidence/policy.v1.json", "sha256": sha256_file(self.policy_path)},
            "guarded_downloader": binding, "authorization_receipt_limit": 1, "new_authorization_receipt": False,
            "source_package": package_binding, "test_report": {"path": "evidence/test-report.v1.json", "sha256": sha256_file(self.test_report_path)},
            "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
        }
        self._write(self.addendum_path, addendum)

    def _authority(self):
        return verify_guarded_download_authority(policy_path=self.policy_path, addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root)

    def _assets(self, *, bad_checksum=False, archive_size=None, content_length=None, redirect=False):
        receipt = json.loads(self.receipt_path.read_text())
        responses = []
        bodies = {}
        for number, target in enumerate(receipt["authorized_targets"]):
            body = (b"x" * archive_size) if archive_size is not None else ("fixture-%s-%s" % (target["kind"], target["date"])).encode()
            digest = hashlib.sha256(body).hexdigest()
            if bad_checksum and number == 0:
                digest = "0" * 64
            checksum = (digest + "  " + Path(target["archive_path"]).name + "\n").encode()
            bodies[target["checksum_url"]] = (checksum, len(checksum), target["checksum_url"])
            bodies[target["archive_url"]] = (body, content_length if content_length is not None else None, "https://evil.example/redirect" if redirect and number == 0 else target["archive_url"])
        def transport(url):
            body, length, final_url = bodies[url]
            response = FakeResponse(body, content_length=length, url=final_url)
            responses.append(response)
            return response
        return transport, responses

    def _run(self, transport, **kwargs):
        return _run_guarded_download_test_only(policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root, manifest_path=self.manifest_path, transport=transport, free_bytes=lambda _: MIN_FREE_AFTER_BYTES + MAX_TOTAL_ARCHIVE_BYTES + 84 * MAX_CHECKSUM_BYTES + 1, **kwargs)

    def _secure_stream(self, *, name, response, per_file_limit, remaining_total, url="https://data.binance.vision/a", expected_url="https://data.binance.vision/a"):
        parent_fd = _open_secure_parent(self.root, Path("direct"))
        try:
            return _stream_to_temp_at(url=url, expected_url=expected_url, parent_fd=parent_fd, temporary_name=name + ".partial", final_name=name, publish_path="direct/" + name, per_file_limit=per_file_limit, remaining_total=remaining_total, transport=lambda _: response, fsync=os.fsync, publish=None)
        finally:
            os.close(parent_fd)

    def test_old_release_is_independently_suspended_and_needs_final_binding(self):
        policy = json.loads(self.policy_path.read_text())
        self.assertEqual(OLD_RELEASE_STATE, policy["parent_release_state"])
        self.addendum_path.unlink()
        with self.assertRaises(GuardedDownloadError):
            self._authority()

    def test_rejects_wrong_parent_scope_or_downloader_binding(self):
        addendum = json.loads(self.addendum_path.read_text()); addendum["parent_authorization"]["receipt_scope_sha256"] = "0" * 64; self._write(self.addendum_path, addendum)
        with self.assertRaises(GuardedDownloadError): self._authority()
        self._write_policy_and_addendum(); policy = json.loads(self.policy_path.read_text()); policy["guarded_downloader"]["sha256"] = "0" * 64; self._write(self.policy_path, policy)
        with self.assertRaises(GuardedDownloadError): self._authority()

    def test_disk_gate_fails_before_any_body_read(self):
        called = []
        def transport(url):
            called.append(url); return FakeResponse(b"unused", url=url)
        with self.assertRaises(GuardedDownloadError):
            _run_guarded_download_test_only(policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root, manifest_path=self.manifest_path, transport=transport, free_bytes=lambda _: MIN_FREE_AFTER_BYTES + MAX_TOTAL_ARCHIVE_BYTES + 84 * MAX_CHECKSUM_BYTES - 1)
        self.assertEqual([], called)
        failure = json.loads((self.root / self.manifest_path).read_text())
        self.assertEqual("FAILED_NOT_ACQUIRED", failure["status"])
        self.assertEqual(84 * MAX_CHECKSUM_BYTES, failure["disk_gate_checks"][0]["remaining_checksum_bytes"])

    def test_dynamic_disk_gate_rechecks_before_second_archive_transport(self):
        transport, responses = self._assets()
        calls = []
        def shrinking_free(_):
            calls.append(1)
            return MIN_FREE_AFTER_BYTES + MAX_TOTAL_ARCHIVE_BYTES + 84 * MAX_CHECKSUM_BYTES + 1 if len(calls) <= 2 else MIN_FREE_AFTER_BYTES - 1
        with self.assertRaises(GuardedDownloadError):
            _run_guarded_download_test_only(policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root, manifest_path=self.manifest_path, transport=transport, free_bytes=shrinking_free)
        self.assertEqual(2, len(responses))
        self.assertTrue(all(response.read_count > 0 for response in responses))
        failure = json.loads((self.root / self.manifest_path).read_text())
        self.assertEqual(3, len(failure["disk_gate_checks"]))

    def test_content_length_limit_fails_before_archive_body_read(self):
        transport, responses = self._assets(content_length=MAX_ARCHIVE_BYTES + 1)
        with self.assertRaises(GuardedDownloadError): self._run(transport)
        archive = next(item for item in responses if item.url.endswith(".zip"))
        self.assertEqual(0, archive.read_count)

    def test_missing_content_length_streams_and_stops_on_per_file_limit(self):
        response = FakeResponse(b"1234", url="https://data.binance.vision/a")
        with self.assertRaises(GuardedDownloadError):
            self._secure_stream(name="overflow.bin", response=response, per_file_limit=3, remaining_total=10)
        self.assertGreater(response.read_count, 0)
        self.assertTrue((self.root / "direct/overflow.bin.partial").exists())

    def test_aggregate_limit_is_enforced_in_stream_path(self):
        response = FakeResponse(b"1234", url="https://data.binance.vision/a")
        with self.assertRaises(GuardedDownloadError):
            self._secure_stream(name="aggregate.bin", response=response, per_file_limit=10, remaining_total=3)

    def test_existing_final_or_temp_refuses_run(self):
        receipt = json.loads(self.receipt_path.read_text()); final = self.root / receipt["authorized_targets"][0]["archive_path"]
        final.parent.mkdir(parents=True, exist_ok=True); final.write_bytes(b"already")
        with self.assertRaises(GuardedDownloadError): self._run(lambda _: self.fail("transport must not run"))

    def test_post_preflight_temp_reservation_race_fails_before_transport(self):
        receipt = json.loads(self.receipt_path.read_text())
        temporary = self.root / (receipt["authorized_targets"][0]["checksum_path"] + ".partial")
        calls = []
        def reserve_after_preflight(_):
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(b"raced")
            return MIN_FREE_AFTER_BYTES + MAX_TOTAL_ARCHIVE_BYTES + 84 * MAX_CHECKSUM_BYTES + 1
        with self.assertRaises(GuardedDownloadError):
            _run_guarded_download_test_only(policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root, manifest_path=self.manifest_path, transport=lambda url: calls.append(url), free_bytes=reserve_after_preflight)
        self.assertEqual([], calls)

    def test_wrong_url_and_redirect_are_refused(self):
        response = FakeResponse(b"x", url="https://data.binance.vision/a")
        with self.assertRaises(GuardedDownloadError):
            self._secure_stream(name="wrong.bin", response=response, per_file_limit=10, remaining_total=10, url="https://data.binance.vision/not-the-receipt")
        transport, _ = self._assets(redirect=True)
        with self.assertRaises(GuardedDownloadError): self._run(transport)

    def test_checksum_mismatch_and_atomic_publish_failure_are_factual_failures(self):
        transport, _ = self._assets(bad_checksum=True)
        with self.assertRaises(GuardedDownloadError): self._run(transport)
        failed = json.loads((self.root / self.manifest_path).read_text())
        self.assertEqual("FAILED_NOT_ACQUIRED", failed["status"])
        target = json.loads(self.receipt_path.read_text())["authorized_targets"][0]
        self.assertFalse((self.root / target["archive_path"]).exists())
        self.assertTrue((self.root / (target["archive_path"] + ".partial")).exists())
        self.tearDown(); self.setUp(); transport, _ = self._assets()
        with self.assertRaises(GuardedDownloadError): self._run(transport, publisher=lambda *args: (_ for _ in ()).throw(OSError("publish failed")))
        self.assertTrue(any(path.suffix == ".partial" for path in (self.root / ".runtime/historical-diagnostic-authorized-download-root").rglob("*")))

    def test_post_preflight_parent_symlink_swap_cannot_escape_workspace(self):
        receipt = json.loads(self.receipt_path.read_text())
        parent = (self.root / receipt["authorized_targets"][0]["archive_path"]).parent
        outside = self.root / "outside"
        outside.mkdir()
        def swap_after_preflight(_):
            parent.mkdir(parents=True, exist_ok=True)
            parent.rmdir()
            parent.symlink_to(outside, target_is_directory=True)
            return MIN_FREE_AFTER_BYTES + MAX_TOTAL_ARCHIVE_BYTES + 84 * MAX_CHECKSUM_BYTES + 1
        with self.assertRaises(GuardedDownloadError):
            _run_guarded_download_test_only(policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root, manifest_path=self.manifest_path, transport=lambda _: self.fail("transport must not run"), free_bytes=swap_after_preflight)
        self.assertEqual([], list(outside.iterdir()))
        self.assertEqual("FAILED_NOT_ACQUIRED", json.loads((self.root / self.manifest_path).read_text())["status"])

    def test_fsync_failure_keeps_factual_failure_manifest_and_partial(self):
        transport, _ = self._assets()
        calls = []
        failed = []
        def failing_fsync(fd):
            calls.append(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode) and not failed:
                failed.append(fd)
                raise OSError("simulated directory fsync failure")
            os.fsync(fd)
        with self.assertRaises(GuardedDownloadError): self._run(transport, fsync=failing_fsync)
        failure = json.loads((self.root / self.manifest_path).read_text())
        self.assertEqual("FAILED_NOT_ACQUIRED", failure["status"])
        self.assertTrue(any(path.suffix == ".partial" for path in (self.root / ".runtime/historical-diagnostic-authorized-download-root").rglob("*")))

    def test_new_secure_directory_entries_are_fsynced_before_descending(self):
        directory = self.root / "new-root"
        directory.mkdir()
        calls = []
        fd = _open_secure_parent(directory, Path("a/b"), fsync=lambda value: calls.append(value))
        try:
            self.assertGreaterEqual(len(calls), 2)
        finally:
            os.close(fd)

    def test_valid_fake_transport_is_one_time_and_cross_validates_acquisition(self):
        transport, _ = self._assets()
        result = self._run(transport)
        self.assertEqual("ACQUIRED_GUARDED_NOT_SCORED", result["status"])
        verified = _verify_guarded_acquisition_manifest_test_only(manifest_path=self.root / self.manifest_path, policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root)
        self.assertTrue(verified["verified"])
        with self.assertRaises(GuardedDownloadError):
            verify_guarded_acquisition_manifest(manifest_path=self.root / self.manifest_path, policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root)
        with self.assertRaises(GuardedDownloadError): self._run(transport)
        receipt = json.loads(self.receipt_path.read_text()); archive = self.root / receipt["authorized_targets"][0]["archive_path"]
        archive.write_bytes(b"tampered")
        with self.assertRaises(GuardedDownloadError):
            _verify_guarded_acquisition_manifest_test_only(manifest_path=self.root / self.manifest_path, policy_path=self.policy_path, final_addendum_path=self.addendum_path, receipt_path=self.receipt_path, contract_path=self.contract_path, plan_path=self.plan_path, workspace_root=self.root)


if __name__ == "__main__":
    unittest.main()
