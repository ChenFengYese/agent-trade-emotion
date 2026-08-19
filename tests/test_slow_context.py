from __future__ import annotations

import ast
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.slow_context import SlowContextError, SlowContextSnapshot, loads_snapshot_json, seal_snapshot, select_context, validate_revision_chain


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64


def stamp(hour: int) -> str:
    return datetime(2026, 1, 1, hour, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def payload(*, source_hour: int = 2, validated_hour: int = 3, expiry_hour: int = 5, unknowns=None, conflicts=None, ordinal: int = 1, parent=None):
    return {
        "snapshot_id": "slow-snapshot-%d" % ordinal,
        "schema_version": "slow-context.v1",
        "instrument_id": "BTCUSDT",
        "context_horizon": "4h",
        "source_cutoff_at": stamp(source_hour),
        "generated_at": stamp(validated_hour - 1),
        "validated_at": stamp(validated_hour),
        "available_at": stamp(max(source_hour, validated_hour)),
        "expires_at": stamp(expiry_hour),
        "facts": [{"claim_id": "fact-1", "statement": "synthetic observed fact", "evidence_ids": ["ev-1"]}],
        "inferences": [{"claim_id": "inference-1", "statement": "synthetic inference", "evidence_ids": ["ev-1"]}],
        "hypotheses": [{"claim_id": "hypothesis-1", "statement": "synthetic hypothesis", "evidence_ids": ["ev-1"]}],
        "unknowns": [] if unknowns is None else unknowns,
        "conflicts": [] if conflicts is None else conflicts,
        "provenance": [{
            "evidence_id": "ev-1", "source_id": "synthetic-source", "source_owner": "synthetic-test-owner",
            "source_url": "synthetic://slow-context/ev-1", "authority_grade": "E",
            "published_at": stamp(0), "retrieved_at": stamp(1), "received_at": stamp(source_hour),
            "source_available_at": stamp(source_hour), "observed_value": "synthetic observation", "unit": "synthetic-unit",
            "methodology": "offline synthetic fixture", "limitations": "not external evidence", "content_sha256": HASH_A,
            "source_kind": "SYNTHETIC", "source_revision_id": "source-r1",
        }],
        "revision": {"revision_id": "context-r", "revision_ordinal": ordinal, "supersedes_snapshot_sha256": parent},
    }


class SlowContextTests(unittest.TestCase):
    def snapshot(self, **kwargs) -> SlowContextSnapshot:
        return SlowContextSnapshot.from_mapping(seal_snapshot(payload(**kwargs)))

    def test_off_and_shadow_are_the_only_modes_and_have_zero_effect(self):
        snapshot = self.snapshot()
        off = select_context("OFF", datetime(2026, 1, 1, 4, tzinfo=UTC), snapshot)
        shadow = select_context("SHADOW", datetime(2026, 1, 1, 4, tzinfo=UTC), snapshot)
        self.assertFalse(off.eligible)
        self.assertTrue(shadow.eligible)
        self.assertEqual("ZERO", off.hot_path_effect)
        self.assertEqual("ZERO", shadow.hot_path_effect)
        with self.assertRaises(SlowContextError):
            select_context("ACTIVE", datetime(2026, 1, 1, 4, tzinfo=UTC), snapshot)

    def test_available_expiry_unknown_conflict_and_missing_boundaries(self):
        snapshot = self.snapshot()
        self.assertEqual("CONTEXT_FUTURE", select_context("SHADOW", datetime(2026, 1, 1, 2, 59, tzinfo=UTC), snapshot).reason_code)
        self.assertEqual("CONTEXT_EXPIRED", select_context("SHADOW", datetime(2026, 1, 1, 5, tzinfo=UTC), snapshot).reason_code)
        self.assertEqual("CONTEXT_MISSING", select_context("SHADOW", datetime(2026, 1, 1, 4, tzinfo=UTC), None).reason_code)
        unknown = self.snapshot(unknowns=[{"unknown_id": "u1", "statement": "synthetic unknown"}])
        self.assertEqual("CONTEXT_UNKNOWN", select_context("SHADOW", datetime(2026, 1, 1, 4, tzinfo=UTC), unknown).reason_code)
        conflict = self.snapshot(conflicts=[{"conflict_id": "c1", "statement": "synthetic conflict", "evidence_ids": ["ev-1"]}])
        self.assertEqual("CONTEXT_CONFLICTED", select_context("SHADOW", datetime(2026, 1, 1, 4, tzinfo=UTC), conflict).reason_code)

    def test_available_at_hash_and_layer_separation_fail_closed(self):
        bad = payload()
        bad["available_at"] = stamp(2)
        with self.assertRaises(SlowContextError):
            seal_snapshot(bad)
        wrong_schema = payload()
        wrong_schema["schema_version"] = "slow-context.v2"
        with self.assertRaises(SlowContextError):
            seal_snapshot(wrong_schema)
        source_delayed = payload(source_hour=4, validated_hour=3, expiry_hour=6)
        source_delayed["generated_at"] = stamp(2)
        with self.assertRaises(SlowContextError):
            seal_snapshot(source_delayed)
        noncanonical = payload()
        noncanonical["validated_at"] = "2026-01-01T03:00:00+00:00"
        with self.assertRaises(SlowContextError):
            seal_snapshot(noncanonical)
        good = seal_snapshot(payload())
        good["snapshot_sha256"] = HASH_B
        with self.assertRaises(SlowContextError):
            SlowContextSnapshot.from_mapping(good)
        repeated = payload()
        repeated["hypotheses"][0]["claim_id"] = "fact-1"
        with self.assertRaises(SlowContextError):
            seal_snapshot(repeated)
        unknown_evidence = payload()
        unknown_evidence["facts"][0]["evidence_ids"] = ["not-present"]
        with self.assertRaises(SlowContextError):
            seal_snapshot(unknown_evidence)
        bad_authority = payload()
        bad_authority["provenance"][0]["authority_grade"] = "Z"
        with self.assertRaises(SlowContextError):
            seal_snapshot(bad_authority)
        bad_source_pit = payload()
        bad_source_pit["provenance"][0]["received_at"] = stamp(0)
        bad_source_pit["provenance"][0]["retrieved_at"] = stamp(1)
        with self.assertRaises(SlowContextError):
            seal_snapshot(bad_source_pit)

    def test_duplicate_keys_nonfinite_and_revision_chain_reject(self):
        with self.assertRaises(SlowContextError):
            loads_snapshot_json('{"snapshot_id":"one","snapshot_id":"two"}')
        with self.assertRaises(SlowContextError):
            loads_snapshot_json('{"value": NaN}')
        first = self.snapshot()
        second = self.snapshot(ordinal=2, parent=first.snapshot_sha256, validated_hour=4, expiry_hour=6)
        self.assertEqual(2, len(validate_revision_chain([first, second])))
        broken = self.snapshot(ordinal=2, parent=HASH_A)
        with self.assertRaises(SlowContextError):
            validate_revision_chain([first, broken])

    def test_sealing_is_deterministic(self):
        first = seal_snapshot(payload())
        second = seal_snapshot(payload())
        self.assertEqual(first, second)
        self.assertEqual(first, SlowContextSnapshot.from_mapping(first).to_dict())
        self.assertEqual(first["snapshot_sha256"], hashlib.sha256(
            b"msta-hed/slow-context-snapshot/v1\x00" + json.dumps({key: value for key, value in first.items() if key != "snapshot_sha256"}, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest())

    def test_contract_self_hash_and_static_prohibitions(self):
        contract = json.loads((ROOT / "config/fast_slow_har1_research_contract.v1.json").read_text(encoding="utf-8"))
        body = dict(contract)
        digest = body.pop("contract_sha256")
        expected = hashlib.sha256(b"msta-hed/fast-slow-har1-research-contract/v1\x00" + json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(expected, digest)
        self.assertEqual(["OFF", "SHADOW"], contract["slow_context"]["allowed_modes"])
        self.assertEqual("ZERO", contract["slow_context"]["hot_path_effect"])
        self.assertEqual("ALL_SNAPSHOT_AND_PROVENANCE_TIMESTAMPS_ARE_CANONICAL_UTC_Z", contract["slow_context"]["canonical_document_time_rule"])
        self.assertIn("authority_grade", contract["slow_context"]["minimum_provenance_fields"])
        forbidden_roots = {"urllib", "requests", "socket", "http", "websockets", "aiohttp", "subprocess", "os", "pathlib"}
        forbidden_names = {"OrderIntent", "PaperBroker", "exec", "eval"}
        for relative in ("trade_system/bar_resampler.py", "trade_system/slow_context.py"):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.split(".")[0] in forbidden_roots for alias in node.names), relative)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden_roots, relative)
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, forbidden_names, relative)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotEqual("open", node.func.id, relative)


if __name__ == "__main__":
    unittest.main()
