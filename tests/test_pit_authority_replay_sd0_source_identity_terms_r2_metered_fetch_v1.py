"""Offline-only tests for the non-activated R2 source/terms draft."""
from __future__ import annotations

import ast
import copy
import hashlib
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from trade_system import pit_authority_replay_sd0_source_identity_terms_r2_metered_fetch_v1 as r2

REPOSITORY = Path(__file__).resolve().parents[1]


def sha(relative: str) -> str:
    return hashlib.sha256((REPOSITORY / relative).read_bytes()).hexdigest()


class R2SourceIdentityTermsDraftTests(unittest.TestCase):
    def test_static_drafts_parse_and_self_hash(self) -> None:
        contract = r2.strict_json((REPOSITORY / r2.CONTRACT_PATH).read_bytes())
        plan = r2.strict_json((REPOSITORY / r2.PLAN_PATH).read_bytes())
        self.assertEqual(contract["contract_sha256"], r2._self("pitar1/sd0-source-identity-terms-r2-measurement-contract/v1", contract, "contract_sha256"))
        self.assertEqual(plan["plan_sha256"], r2._self("pitar1/sd0-source-identity-terms-r2-request-plan/v1", plan, "plan_sha256"))

    def test_plan_is_nonexecuting_and_does_not_invent_license_or_url(self) -> None:
        _, plan = r2.load_draft(REPOSITORY)
        self.assertEqual([], plan["requests"])
        self.assertEqual("DENIED_PENDING_INDEPENDENT_SOL_GATE", plan["activation_status"])
        self.assertIn("NO_ASSUMED_LICENSE_FILENAME", plan["no_inferred_resources"])
        self.assertEqual("WAIT_DATA_PRODUCTION_ACTIVATION_DENIED", r2.production_activation_status(REPOSITORY))

    def test_redirect_and_404_fail_closed_without_transport(self) -> None:
        base = {"exact_url": "https://official.example/terms", "effective_url": "https://official.example/terms", "method": "GET", "status_code": 200, "response_body_bytes": 10, "response_header_bytes": 100, "elapsed_monotonic_ns": 1, "tls_validation_result": "VALIDATED", "proxy_endpoint": "http://127.0.0.1:7897", "redirect_chain": [], "response_body_sha256": "0" * 64}
        redirected = copy.deepcopy(base); redirected["effective_url"] = "https://other.example/terms"; redirected["redirect_chain"] = [base["exact_url"]]
        with self.assertRaises(r2.R2Error) as redirect_error:
            r2.validate_observation_shape(redirected)
        self.assertEqual("HALT_PROTOCOL_VIOLATION", redirect_error.exception.state)
        missing = copy.deepcopy(base); missing["status_code"] = 404; missing["response_body_bytes"] = 0
        with self.assertRaises(r2.R2Error) as missing_error:
            r2.validate_observation_shape(missing)
        self.assertEqual("WAIT_DATA_TERMS_D0_DENIED", missing_error.exception.state)

    def test_ambiguity_and_explicit_allowance_do_not_self_authorize(self) -> None:
        ambiguous = {scope: "SILENT_OR_AMBIGUOUS" for scope in r2.INTENDED_SCOPES}
        result = r2.assess_terms(ambiguous, actor="researcher", jurisdiction="CN", repository_identity_complete=True)
        self.assertEqual("WAIT_DATA_TERMS_D0_DENIED", result.terminal_disposition)
        allowed = {scope: "EXPLICITLY_ALLOWED" for scope in r2.INTENDED_SCOPES}
        result = r2.assess_terms(allowed, actor="researcher", jurisdiction="CN", repository_identity_complete=True)
        self.assertEqual("WAIT_DATA_PRODUCTION_ACTIVATION_DENIED", result.terminal_disposition)
        self.assertEqual("DENIED", result.production_activation)

    def test_predecessor_evidence_is_read_only_and_unchanged(self) -> None:
        before = {relative: sha(relative) for relative in r2.PREDECESSOR_IDENTITIES}
        r2.load_draft(REPOSITORY)
        self.assertEqual(before, {relative: sha(relative) for relative in before})

    def test_path_conflict_or_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"; target.write_text("{}", encoding="utf-8")
            unsafe = root / "nested" / "required.json"; unsafe.parent.mkdir()
            unsafe.symlink_to(target)
            with self.assertRaises(r2.R2Error) as raised:
                r2._safe_read(root, "nested/required.json")
        self.assertEqual("HALT_PROTOCOL_VIOLATION", raised.exception.state)

    def test_client_has_no_network_or_implicit_entrypoint(self) -> None:
        tree = ast.parse(Path(r2.__file__).read_text())
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
        self.assertFalse({"socket", "http", "urllib", "requests", "ssl"} & imports)
        self.assertFalse(any(isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and any(isinstance(item, ast.Name) and item.id == "__name__" for item in ast.walk(node.test)) for node in ast.walk(tree)))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
