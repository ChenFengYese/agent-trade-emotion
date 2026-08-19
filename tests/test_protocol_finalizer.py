import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_system.g1_report import G1ReportError, write_g1_report
from trade_system.protocol import ProtocolError, ResearchProtocol
from trade_system.protocol_finalizer import finalize_research_protocol


ROOT = Path(__file__).resolve().parents[1]


class ProtocolFinalizerTests(unittest.TestCase):
    def _guard(self) -> Path:
        return ROOT / "config" / "research_protocol_supersession.v2.json"

    def _pass_report(self, path: Path, *, passed=True, policy_sha="5d8f43024f0e9e07198ad2546220a674f6afc2b2f160c10cee7364395e318d32"):
        return write_g1_report(path, {
            "passed": passed,
            "status": "PASS" if passed else "WAIT_DATA",
            "policy_id": "g1-binance-usdm-btcusdt-forward-v1",
            "policy_sha256": policy_sha,
            "requirements": {
                "source_registry_id": "source-registry.v3",
                "source_registry_sha256": "3aa28782ff3c0af5be5ad0bc98e690af87dbe2c57687d6ab61b1549bae74ec4b",
            },
        })

    def _complete_v2_pending(self, path: Path) -> None:
        raw = json.loads((ROOT / "config" / "research_protocol.v2.draft.json").read_text(encoding="utf-8"))
        raw["status"] = "PREREGISTERED_PENDING_G1"
        for role in raw["data_eligibility"]["admitted_collection_roles"]:
            role["capture_plan"] = {"id": "%s-plan.v2" % role["role"].lower(), "sha256": "a" * 64}
            role["acceptance_policy"] = {"id": "%s-quality.v2" % role["role"].lower(), "sha256": "b" * 64}
            role["quality_equivalence"]["comparison_rule"] = "EQUAL_OR_STRICTER_THAN_G1"
        raw["data_eligibility"]["admitted_collection_roles"][0]["time_window"] = {
            "decision_start": "2026-08-01T00:00:00Z", "decision_end": "2026-08-31T23:55:00Z", "label_horizon_seconds": 300,
        }
        # Non-final fixture only: production draft deliberately leaves these
        # response fields REQUIRED until the context pipeline emits them.
        for terms in raw["g2_evaluator"]["feature_groups"].values():
            for term in terms:
                term["sources"] = ["synthetic_R_directional" if value == "REQUIRED:R_directional" else "synthetic_R_improvement" if value == "REQUIRED:R_directional_improvement" else value for value in term.get("sources", [])]
        raw["context_evidence"] = {"policy": {"id": "synthetic-context", "sha256": "d" * 64}, "artifact": {"sha256": "e" * 64, "manifest_sha256": "f" * 64}, "role_window": {"id": "synthetic-window", "sha256": "a" * 64}, "archive_receipts": {"schema_version": "evidence-archive-receipt.v1", "require_verified_per_collection": True}}
        for binding in raw["software_bindings"].values():
            binding["component_id"] = "component.v2"
            binding["source_sha256"] = "c" * 64
        path.write_text(json.dumps(raw), encoding="utf-8")

    def test_superseded_v1_is_rejected_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = self._pass_report(root / "g1.json")
            output = root / "frozen.json"
            with self.assertRaises(ProtocolError):
                finalize_research_protocol(
                    ROOT / "config" / "research_protocol.preregistered.v1.json",
                    g1_report_path=root / "g1.json", output_path=output,
                    supersession_guard_path=self._guard(),
                )
            self.assertFalse(output.exists())

    def test_v2_only_g1_binding_and_freeze_fields_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = self._pass_report(root / "g1.json")
            pending_path = root / "v2.pending.json"
            self._complete_v2_pending(pending_path)
            output = root / "frozen.json"
            result = finalize_research_protocol(
                pending_path,
                g1_report_path=root / "g1.json",
                output_path=output,
                supersession_guard_path=self._guard(),
                frozen_at="2026-07-30T00:00:00Z",
            )
            frozen = ResearchProtocol.load(output)
            self.assertTrue(frozen.is_frozen_for_research)
            with patch("trade_system.protocol.ProtocolSupersessionGuard.load") as load_guard:
                frozen.assert_frozen_for_research()
                load_guard.assert_not_called()
            self.assertEqual(report["report_sha256"], frozen.raw["data_eligibility"]["g1_qualification"]["required_g1_report_sha256"])
            self.assertEqual("DENIED_BY_PROTOCOL", result["live_trading_authorization"])
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            persisted = json.loads(output.read_text(encoding="utf-8"))
            persisted["status"] = pending["status"]
            persisted.pop("frozen_at")
            persisted["data_eligibility"]["g1_qualification"]["required_g1_report_sha256"] = "PENDING_VERIFIED_PASS_REPORT"
            self.assertEqual(pending, persisted)
            persisted["status"] = "FROZEN_RESEARCH_PROTOCOL"
            persisted["frozen_at"] = "2026-07-30T00:00:00Z"
            persisted["data_eligibility"]["g1_qualification"]["required_g1_report_sha256"] = report["report_sha256"]
            persisted["protocol_lineage"]["finalization_guard"] = {"guard_id": "self-authored-guard", "sha256": "f" * 64}
            forged = root / "forged-frozen-v2.json"
            forged.write_text(json.dumps(persisted), encoding="utf-8")
            forged_protocol = ResearchProtocol.load(forged)
            with self.assertRaises(ProtocolError):
                forged_protocol.assert_frozen_for_research()

    def test_non_pass_or_wrong_policy_never_creates_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._pass_report(root / "g1.json", passed=False)
            pending_path = root / "v2.pending.json"
            self._complete_v2_pending(pending_path)
            output = root / "frozen.json"
            with self.assertRaises(G1ReportError):
                finalize_research_protocol(
                    pending_path,
                    g1_report_path=root / "g1.json", output_path=output,
                    supersession_guard_path=self._guard(),
                )
            self.assertFalse(output.exists())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._pass_report(root / "g1.json", policy_sha="a" * 64)
            pending_path = root / "v2.pending.json"
            self._complete_v2_pending(pending_path)
            output = root / "frozen.json"
            with self.assertRaises(ProtocolError):
                finalize_research_protocol(
                    pending_path,
                    g1_report_path=root / "g1.json", output_path=output,
                    supersession_guard_path=self._guard(),
                )
            self.assertFalse(output.exists())

    def test_non_v2_or_mutated_legacy_pending_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._pass_report(root / "g1.json")
            base = json.loads((ROOT / "config" / "research_protocol.preregistered.v1.json").read_text(encoding="utf-8"))
            variants = []
            mutated = dict(base)
            mutated["notice"] = str(mutated["notice"]) + " changed"
            variants.append(mutated)
            renamed = dict(base)
            renamed["protocol_id"] = "new-v1-pending"
            variants.append(renamed)
            for index, raw in enumerate(variants):
                pending = root / ("legacy-%d.json" % index)
                output = root / ("legacy-%d.frozen.json" % index)
                pending.write_text(json.dumps(raw), encoding="utf-8")
                with self.assertRaises(ProtocolError):
                    finalize_research_protocol(
                        pending, g1_report_path=root / "g1.json", output_path=output,
                        supersession_guard_path=self._guard(),
                    )
                self.assertFalse(output.exists())

    def test_v2_rejects_self_authored_supersession_guard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._pass_report(root / "g1.json")
            pending = root / "v2.pending.json"
            self._complete_v2_pending(pending)
            raw = json.loads(pending.read_text(encoding="utf-8"))
            guard_raw = json.loads(self._guard().read_text(encoding="utf-8"))
            guard_raw["guard_id"] = "self-authored-guard"
            guard = root / "self-authored-guard.json"
            guard.write_text(json.dumps(guard_raw), encoding="utf-8")
            from trade_system.protocol import canonical_sha256
            raw["protocol_lineage"]["finalization_guard"] = {
                "guard_id": "self-authored-guard", "sha256": canonical_sha256(guard_raw),
            }
            pending.write_text(json.dumps(raw), encoding="utf-8")
            output = root / "frozen.json"
            with self.assertRaises(ProtocolError):
                finalize_research_protocol(
                    pending, g1_report_path=root / "g1.json", output_path=output,
                    supersession_guard_path=guard,
                )
            self.assertFalse(output.exists())
