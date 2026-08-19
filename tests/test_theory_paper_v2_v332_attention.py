from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.attention import (
    AttentionApplicationError,
    AttentionService,
)
from trade_system.theory_paper_v2.domain.market_cycle import attention as attention_domain
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    AttentionRepositoryCASConflict,
    FileAttentionRepository,
)


class V332AttentionCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = FileAttentionRepository(self.root)
        self.sessions = AgentSessionService(self.repository)
        self.attention = AttentionService(self.repository)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _registry(
        logical_agent_id: str = "HYPE_TRADER",
        symbol: str = "HYPEUSDT",
        *,
        continuity_nonce: str = "ctx-hype-g1",
        physical_task_id: str = "task-hype-g1",
    ) -> AgentRegistry:
        return AgentRegistry(
            logical_agent_id=logical_agent_id,
            symbol=symbol,
            generation=1,
            continuity_nonce=continuity_nonce,
            physical_task_id=physical_task_id,
            status="ACTIVE",
            registered_at="2026-08-13T00:00:00+00:00",
        )

    @staticmethod
    def _request(
        request_id: str = "next-check-hype-001",
        *,
        logical_agent_id: str = "HYPE_TRADER",
        symbol: str = "HYPEUSDT",
        generation: int = 1,
        continuity_nonce: str = "ctx-hype-g1",
        issued_at: str = "2026-08-13T00:00:01+00:00",
        earliest_wake_at: str = "2026-08-13T00:05:00+00:00",
        latest_useful_at: str = "2026-08-13T00:10:00+00:00",
        supersedes: str | None = None,
        requested_focus: str = "Re-check the Agent-selected path invalidation.",
    ) -> AttentionRequest:
        return AttentionRequest(
            request_id=request_id,
            logical_agent_id=logical_agent_id,
            agent_generation=generation,
            continuity_nonce=continuity_nonce,
            symbol=symbol,
            mode="WAKE_AFTER",
            issued_at=issued_at,
            continue_until=None,
            earliest_wake_at=earliest_wake_at,
            latest_useful_at=latest_useful_at,
            reason_summary="The trading Goal chose its next review window.",
            requested_focus=requested_focus,
            hypothesis_or_episode_ref="episode-hype-001",
            position_and_open_order_ref="paper-state-hype-001",
            data_cursor="cursor-hype-001",
            supersedes=supersedes,
        )

    def test_checkpoint_append_replay_and_exact_idempotency(self) -> None:
        self.sessions.register(self._registry())
        request = self._request()
        accepted = self.attention.submit_request(
            request, received_at="2026-08-13T00:00:02+00:00"
        )
        revision = self.attention.status("HYPE_TRADER").revision
        duplicate = self.attention.submit_request(
            request, received_at="2026-08-13T00:00:02+00:00"
        )
        self.assertEqual(accepted, duplicate)
        self.assertEqual(revision, self.attention.status("HYPE_TRADER").revision)

        restarted = AttentionService(FileAttentionRepository(self.root))
        state = restarted.status("HYPE_TRADER")
        self.assertEqual(request, state.request(request.request_id))
        self.assertEqual(
            "2026-08-13T00:00:02+00:00",
            state.request_accepted_ats[request.request_id],
        )
        self.assertEqual("PENDING", state.request_statuses[request.request_id])
        self.assertEqual(request.request_id, state.active_request_id)
        self.assertEqual(
            list(range(1, state.revision + 1)),
            [event.revision for event in self.repository.replay("HYPE_TRADER")],
        )
        raw_event = self.repository.replay("HYPE_TRADER")[-1]
        self.assertNotIn("goal_checkpoint", raw_event.payload)

    def test_new_checkpoint_explicitly_supersedes_previous(self) -> None:
        self.sessions.register(self._registry())
        first = self._request()
        self.attention.submit_request(first)
        with self.assertRaises(AttentionApplicationError):
            self.attention.submit_request(
                self._request(
                    "next-check-hype-missing-link",
                    issued_at="2026-08-13T00:01:00+00:00",
                    earliest_wake_at="2026-08-13T00:06:00+00:00",
                    latest_useful_at="2026-08-13T00:11:00+00:00",
                )
            )
        second = self._request(
            "next-check-hype-002",
            issued_at="2026-08-13T00:01:00+00:00",
            earliest_wake_at="2026-08-13T00:06:00+00:00",
            latest_useful_at="2026-08-13T00:11:00+00:00",
            supersedes=first.request_id,
        )
        self.attention.submit_request(second)
        state = self.attention.status("HYPE_TRADER")
        self.assertEqual("SUPERSEDED", state.request_statuses[first.request_id])
        self.assertEqual("PENDING", state.request_statuses[second.request_id])
        self.assertEqual(second.request_id, state.active_request_id)

    def test_generation_plus_one_recovers_same_logical_goal(self) -> None:
        self.sessions.register(self._registry())
        prior = self._request()
        self.attention.submit_request(prior)
        recovered = self.sessions.recover_generation(
            "HYPE_TRADER",
            failed_generation=1,
            new_physical_task_id="task-hype-g2",
            new_continuity_nonce="ctx-hype-g2",
            resume_capsule_ref="resume-hype-g1",
            recovered_at="2026-08-13T00:04:00+00:00",
        )
        self.assertEqual(2, recovered.generation)
        self.assertEqual("ctx-hype-g1", recovered.prior_continuity_nonce)
        self.assertEqual(recovered, self.sessions.current("HYPE_TRADER"))
        self.assertEqual(
            recovered,
            self.sessions.recover_generation(
                "HYPE_TRADER",
                failed_generation=1,
                new_physical_task_id="task-hype-g2",
                new_continuity_nonce="ctx-hype-g2",
                resume_capsule_ref="resume-hype-g1",
                recovered_at="2026-08-13T00:04:00+00:00",
            ),
        )
        next_request = self._request(
            "next-check-hype-g2",
            generation=2,
            continuity_nonce="ctx-hype-g2",
            issued_at="2026-08-13T00:04:01+00:00",
            earliest_wake_at="2026-08-13T00:08:00+00:00",
            latest_useful_at="2026-08-13T00:12:00+00:00",
            supersedes=prior.request_id,
        )
        self.attention.submit_request(next_request)
        self.assertEqual(
            next_request.request_id,
            self.attention.status("HYPE_TRADER").active_request_id,
        )

    def test_assets_have_isolated_streams_and_symbol_bindings(self) -> None:
        self.sessions.register(self._registry())
        self.sessions.register(
            self._registry(
                "SNDK_TRADER",
                "SNDKUSDT",
                continuity_nonce="ctx-sndk-g1",
                physical_task_id="task-sndk-g1",
            )
        )
        self.attention.submit_request(self._request("next-check-shared-001"))
        self.attention.submit_request(
            self._request(
                "next-check-shared-001",
                logical_agent_id="SNDK_TRADER",
                symbol="SNDKUSDT",
                continuity_nonce="ctx-sndk-g1",
            )
        )
        self.assertEqual(
            "HYPEUSDT",
            self.attention.status("HYPE_TRADER")
            .requests["next-check-shared-001"]
            .symbol,
        )
        self.assertEqual(
            "SNDKUSDT",
            self.attention.status("SNDK_TRADER")
            .requests["next-check-shared-001"]
            .symbol,
        )
        with self.assertRaises(AttentionApplicationError):
            self.attention.submit_request(
                self._request(
                    "next-check-hype-bad-symbol",
                    symbol="SNDKUSDT",
                    supersedes="next-check-shared-001",
                )
            )

    def test_checkpoint_identity_time_and_mutation_fail_closed(self) -> None:
        self.sessions.register(self._registry())
        request = self._request()
        self.attention.submit_request(request)
        with self.assertRaises(FrozenInstanceError):
            request.requested_focus = "runtime replacement"  # type: ignore[misc]
        with self.assertRaises(AttentionApplicationError):
            self.attention.submit_request(
                replace(request, requested_focus="runtime replacement")
            )
        with self.assertRaises(AttentionApplicationError):
            self.attention.submit_request(
                replace(request, request_id="next-check-late"),
                received_at="2026-08-13T00:10:01+00:00",
            )

    def test_repository_compare_and_swap_rejects_stale_writer(self) -> None:
        self.repository.compare_and_swap(
            "HYPE_TRADER",
            expected_revision=0,
            event_id="test-event-1",
            event_type="TEST_EVENT",
            occurred_at="2026-08-13T00:00:00+00:00",
            payload={"value": 1},
        )
        with self.assertRaises(AttentionRepositoryCASConflict):
            self.repository.compare_and_swap(
                "HYPE_TRADER",
                expected_revision=0,
                event_id="test-event-2",
                event_type="TEST_EVENT",
                occurred_at="2026-08-13T00:00:01+00:00",
                payload={"value": 2},
            )

    def test_supervisor_wake_surface_and_events_are_absent(self) -> None:
        self.sessions.register(self._registry())
        self.assertFalse(hasattr(self.sessions, "build_wake_packet"))
        self.assertFalse(hasattr(self.attention, "submit_goal_checkpoint"))
        for name in (
            "admit_request",
            "expire_request",
            "prepare_dispatch",
            "dispatch_once",
            "mark_dispatched",
            "acknowledge_dispatch",
            "complete_dispatch",
            "recover_dispatch",
        ):
            self.assertFalse(hasattr(self.attention, name), name)
        for name in ("WakeReceipt", "WakePacket", "WakeDispatch"):
            self.assertFalse(hasattr(attention_domain, name), name)

        self.repository.compare_and_swap(
            "HYPE_TRADER",
            expected_revision=1,
            event_id="legacy-wake-receipt",
            event_type="WAKE_RECEIPT_RECORDED",
            occurred_at="2026-08-13T00:00:01+00:00",
            payload={},
        )
        with self.assertRaisesRegex(
            AttentionApplicationError, "ATTENTION_EVENT_TYPE_UNKNOWN"
        ):
            self.attention.status("HYPE_TRADER")


if __name__ == "__main__":
    unittest.main()
