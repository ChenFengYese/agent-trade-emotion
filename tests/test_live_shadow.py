import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from trade_system.binance import BinanceCaptureSession
from trade_system.cli import main
from trade_system.event_store import EventStore
from trade_system.live_shadow import LiveFeatureObserver
from trade_system.market_runtime import BinancePublicMarketRuntime
from trade_system.replay import DeterministicReplay


class LiveShadowTests(unittest.TestCase):
    def test_sealed_live_feature_artifact_matches_its_collection_replay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "evidence"
            store = EventStore(root)
            collection_id = "live-shadow-1"
            observer = LiveFeatureObserver(Path("derived/live-features.ndjson"), evidence_root=root)
            runtime = BinancePublicMarketRuntime(
                depth_session=BinanceCaptureSession(store, collection_id + "-depth"),
                market_session=BinanceCaptureSession(store, collection_id + "-market"),
                feature_observer=observer.observe,
            )
            runtime.apply_snapshot({"lastUpdateId": 100, "bids": [["99", "2"]], "asks": [["101", "2"]]})
            runtime.process_envelope("market", {"stream": "btcusdt@aggTrade", "data": {
                "e": "aggTrade", "E": 1700000000000, "a": 1, "p": "100", "q": "1", "m": False,
            }})
            runtime.process_envelope("depth", {"stream": "btcusdt@depth@100ms", "data": {
                "e": "depthUpdate", "E": 1700000000100, "U": 101, "u": 101, "pu": 100,
                "b": [["99", "3"]], "a": [],
            }})
            artifact = observer.finalize().to_dict()
            valid, issues, audit_digest = store.audit()
            self.assertTrue(valid, issues)
            store.write_collection_manifest(collection_id, {
                "collection_result": "QUALIFIED_SMOKE",
                "audit_digest": audit_digest,
                "replay_digest": DeterministicReplay(store).digest(),
                "live_feature_artifact": artifact,
            })
            segment = Path(next(store.iter_raw()).raw_segment).stem
            store.seal_raw_segment(segment)

            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "verify-live-feature-shadow", "--data-dir", str(root), "--collection-id", collection_id,
                    "--live-features", artifact["path"],
                ])
            self.assertEqual(0, result)
            report = json.loads(stdout.getvalue())
            self.assertTrue(report["passed"])
            self.assertGreater(report["matched_rows"], 0)

            with Path(artifact["path"]).open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                altered = main([
                    "verify-live-feature-shadow", "--data-dir", str(root), "--collection-id", collection_id,
                    "--live-features", artifact["path"],
                ])
            self.assertEqual(2, altered)
            self.assertIn("digest does not match", stderr.getvalue())
