import json
import tempfile
import unittest
from pathlib import Path

from trade_system.source_registry import SourceRegistry, SourceRegistryError


class SourceRegistryTests(unittest.TestCase):
    def _write_registry(self, path: Path, *, channels=None):
        path.write_text(json.dumps({
            "registry_id": "source-registry.v1",
            "schema_version": "source-registry-v1",
            "status": "FROZEN_SOURCE_REGISTRY",
            "frozen_at": "2026-01-01T00:00:00Z",
            "sources": [{
                "source_id": "SRC-TEST-WS",
                "venue": "TEST",
                "instrument_scope": ["BTCUSDT"],
                "transport": "WEBSOCKET",
                "endpoints": ["wss://example.test/stream"],
                "channels": channels or ["{symbol}@trade"],
                "schema_version": "test-v1",
                "permission": "PUBLIC",
                "region_constraints": "none",
                "coverage_semantics": "observed only",
            }],
        }), encoding="utf-8")

    def test_manifest_binding_is_digest_pinned_and_resolves_symbol_template(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.json"
            self._write_registry(path)
            registry = SourceRegistry.load(path)
            binding = registry.manifest_binding("BTCUSDT", ["btcusdt@trade"])
            self.assertEqual("source-registry.v1", binding["registry_id"])
            self.assertEqual(["SRC-TEST-WS"], binding["source_ids"])
            self.assertRegex(binding["sha256"], r"^[0-9a-f]{64}$")

    def test_unregistered_capture_stream_is_rejected_before_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.json"
            self._write_registry(path)
            registry = SourceRegistry.load(path)
            with self.assertRaisesRegex(SourceRegistryError, "configured streams absent"):
                registry.manifest_binding("BTCUSDT", ["btcusdt@forceOrder"])

    def test_registry_rejects_unzoned_freeze_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.json"
            self._write_registry(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["frozen_at"] = "2026-01-01T00:00:00"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(SourceRegistryError, "timestamp with timezone"):
                SourceRegistry.load(path)
