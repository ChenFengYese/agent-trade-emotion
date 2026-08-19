from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from trade_system.theory_paper_v2.domain import v32_agent_lifecycle as lifecycle
from trade_system.theory_paper_v2.domain import (
    v32_current_root_agent_mailbox as presentation,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    build_v32_agent_input_context_v1,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_agent_input_context_v1,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID,
    SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_shard_selection_v1,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD,
    build_v32_current_codex_presentation_envelope_v1,
    build_v32_current_root_agent_mailbox_claim_v1,
    build_v32_current_root_agent_mailbox_request_v1,
    claim_v32_current_root_agent_mailbox_request_v1,
    open_v32_current_root_agent_mailbox_request_v1,
    verify_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
)


NOW = "2026-08-07T00:16:00Z"


def _binding(
    name: str, document: dict, schema_id: str, digest_field: str
) -> dict[str, str]:
    return lifecycle_fixture._embedded(name, document, schema_id, digest_field)


def _lossless_package(packet: dict, packet_binding: dict) -> dict:
    bundle = build_v32_context_compaction_bundle_v1(
        run_id=packet["run_id"],
        cycle_index=packet["cycle_index"],
        created_at=NOW,
        source_artifacts=[
            {
                "artifact_binding": packet_binding,
                "canonical_bytes": len(canonical_bytes(packet)),
            }
        ],
        original_documents=[packet],
        max_shard_canonical_bytes=65_536,
    )
    manifest = bundle["manifest"]
    shards = bundle["shards"]
    manifest_binding = _binding(
        "lossless/manifest", manifest, MANIFEST_SCHEMA_ID, MANIFEST_DIGEST_FIELD
    )
    shard_bindings = [
        _binding(
            f"lossless/shard-{index:04d}",
            shard,
            SHARD_SCHEMA_ID,
            SHARD_DIGEST_FIELD,
        )
        for index, shard in enumerate(shards)
    ]
    selection = build_v32_context_shard_selection_v1(
        manifest=manifest,
        manifest_binding=manifest_binding,
        shards=shards,
        original_documents=[packet],
        caller_required_member_ids=[],
        selected_at=NOW,
        max_agent_context_canonical_bytes=1_048_576,
        shard_bindings=shard_bindings,
    )
    return {
        "manifest": manifest,
        "shards": shards,
        "original_documents": [packet],
        "selection": selection,
        "manifest_binding": manifest_binding,
        "shard_bindings": shard_bindings,
        "selection_binding": _binding(
            "lossless/selection",
            selection,
            SELECTION_SCHEMA_ID,
            SELECTION_DIGEST_FIELD,
        ),
    }


class V32LosslessAgentDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = lifecycle_fixture._proposal_packet()
        cls.packet_binding = _binding(
            "lossless/proposal-packet",
            cls.packet,
            PROPOSAL_PACKET_SCHEMA_ID,
            PROPOSAL_PACKET_DIGEST_FIELD,
        )
        cls.package = _lossless_package(cls.packet, cls.packet_binding)
        if len(cls.package["shards"]) < 2:
            raise AssertionError("fixture must exercise ordered multi-shard delivery")
        with mock.patch.object(
            lifecycle, "MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES", 300 * 1024
        ):
            cls.context = build_v32_agent_input_context_v1(
                agent_stage="PROPOSAL",
                canonical_packet=cls.packet,
                canonical_packet_binding=cls.packet_binding,
                created_at=NOW,
                lossless_context_package=cls.package,
            )
        cls.context_binding = _binding(
            "lossless/proposal-context",
            cls.context,
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )

    def test_forced_all_shards_reconstructs_the_exact_original(self) -> None:
        selection = self.package["selection"]
        self.assertEqual(self.context["context_delivery_mode"], "LOSSLESS_SHARDED")
        self.assertIsNone(self.context["canonical_packet"])
        self.assertEqual(
            selection["selected_member_count"],
            self.package["manifest"]["member_count"],
        )
        self.assertEqual(
            selection["selected_shard_count"], len(self.package["shards"])
        )
        self.assertEqual(
            verify_v32_agent_input_context_v1(
                self.context, lossless_context_package=self.package
            ),
            self.context[AGENT_INPUT_CONTEXT_DIGEST_FIELD],
        )
        self.assertEqual(
            resolve_v32_agent_canonical_packet_v1(
                self.context, lossless_context_package=self.package
            ),
            self.packet,
        )

    def test_production_presentation_cap_rejects_before_mailbox_write(self) -> None:
        with TemporaryDirectory() as temporary:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(temporary))
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{self.packet['run_id']}::0001",
                run_id=self.packet["run_id"],
                cycle_index=1,
                created_at=NOW,
            )
            with self.assertRaisesRegex(
                ValueError, "V32_MAILBOX_STORE_INLINE_ONLY"
            ):
                mailbox.enqueue_request(
                    run_id=self.packet["run_id"],
                    cycle_index=1,
                    expected_checkpoint_digest=checkpoint[
                        CHECKPOINT_DIGEST_FIELD
                    ],
                    agent_input_context=self.context,
                    agent_input_context_binding=self.context_binding,
                    reserved_at="2026-08-07T00:16:05Z",
                    lossless_context_package=self.package,
                )
            after = mailbox.load_checkpoint(
                run_id=self.packet["run_id"], cycle_index=1
            )
            self.assertEqual(after, checkpoint)
            self.assertFalse(any(Path(temporary).rglob("request.json")))
            self.assertFalse(any(Path(temporary).rglob("input-material")))

    def test_owning_verifier_requires_the_complete_sharded_package(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "V32_AGENT_INPUT_DURABLE_ORIGINAL_REQUIRED"
        ):
            verify_v32_agent_input_context_v1(self.context)

    def test_unqualified_sharded_domain_presentation_is_mechanically_lossless(self) -> None:
        with TemporaryDirectory() as temporary:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(temporary))
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{self.packet['run_id']}::0001",
                run_id=self.packet["run_id"],
                cycle_index=1,
                created_at=NOW,
            )
            request = build_v32_current_root_agent_mailbox_request_v1(
                mailbox_id=checkpoint["mailbox_id"],
                agent_input_context=self.context,
                agent_input_context_binding=self.context_binding,
                reserved_at="2026-08-07T00:16:05Z",
            )
            opened_checkpoint = open_v32_current_root_agent_mailbox_request_v1(
                checkpoint=checkpoint,
                request=request,
            )
            claim = build_v32_current_root_agent_mailbox_claim_v1(
                request=request,
                claimed_at="2026-08-07T00:16:10Z",
            )
            claimed_checkpoint = claim_v32_current_root_agent_mailbox_request_v1(
                checkpoint=opened_checkpoint,
                request=request,
                claim=claim,
            )
            # This deliberately raises the cap only around a pure domain
            # mechanics check.  The production mailbox above remains
            # INLINE_ONLY and never accepts this object.
            with mock.patch.object(
                presentation,
                "MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES",
                32 * 1024 * 1024,
            ):
                envelope = build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=claimed_checkpoint,
                    request=request,
                    claim=claim,
                    lossless_context_package=self.package,
                    control_context={
                        "presentation_kind": "MAILBOX_AGENT_CLAIM",
                        "stage": "PROPOSAL",
                        "stage_status": "CLAIMED",
                        "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                    },
                )
                verify_v32_current_codex_presentation_envelope_v1(envelope)
            self.assertEqual(
                envelope["input_document_representation"],
                "SHARDED_PACKAGE_DOCUMENTS_ONCE",
            )
            self.assertEqual(
                canonical_bytes(envelope).count(canonical_bytes(self.packet)),
                1,
            )

    def test_omitted_reordered_or_tampered_shards_fail_closed(self) -> None:
        omitted = deepcopy(self.package)
        omitted["shards"].pop()
        omitted["shard_bindings"].pop()
        with self.assertRaises(ValueError):
            verify_v32_agent_input_context_v1(
                self.context, lossless_context_package=omitted
            )

        reordered = deepcopy(self.package)
        reordered["shards"] = list(reversed(reordered["shards"]))
        reordered["shard_bindings"] = list(
            reversed(reordered["shard_bindings"])
        )
        with self.assertRaises(ValueError):
            verify_v32_agent_input_context_v1(
                self.context, lossless_context_package=reordered
            )

        tampered = deepcopy(self.package)
        tampered["shards"][0]["member_rows"][0]["json_pointer"] = "/tampered"
        tampered["shards"][0] = self_digest(
            tampered["shards"][0], SHARD_DIGEST_FIELD
        )
        tampered["shard_bindings"][0] = _binding(
            "lossless/tampered-shard",
            tampered["shards"][0],
            SHARD_SCHEMA_ID,
            SHARD_DIGEST_FIELD,
        )
        with self.assertRaises(ValueError):
            verify_v32_agent_input_context_v1(
                self.context, lossless_context_package=tampered
            )

if __name__ == "__main__":
    unittest.main()
