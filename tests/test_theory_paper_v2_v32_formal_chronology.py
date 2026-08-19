from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from tests.test_theory_paper_v2_v32_dynamic_research import _kwargs
from tests.test_theory_paper_v2_v32_public_source_collector import (
    BASE,
    RUN_ID,
    SequenceClock,
    authority,
    raw_bundle,
    ts,
)
from trade_system.theory_paper_v2.application.v32_dynamic_state_continuity import (
    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    RECEIPT_DIGEST_FIELD,
    build_v32_verified_pit_evidence_availability_registry_v1,
    compose_v32_dynamic_state_continuity_v1,
    verify_v32_dynamic_state_continuity_v1,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    build_v32_dynamic_research_state_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_bundle_transport import (
    V32OkxPublicBundleTransport,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_https_route import (
    V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_market_graph_projection import (
    GRAPH_REGISTRY_DIGEST_FIELD,
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    V32RawFirstOkxPublicBundleCollector,
)


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class _Response:
    def __init__(self, body: str) -> None:
        self.status = 200
        self._body = body.encode("utf-8")
        self._url: str | None = None

    def read(self, amount: int = -1) -> bytes:
        return self._body if amount < 0 else self._body[:amount]

    def geturl(self) -> str:
        assert self._url is not None
        return self._url

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Opener:
    route_policy_id = V32_PUBLIC_HTTPS_ROUTE_POLICY_ID

    def __init__(self, bodies: list[str]) -> None:
        self._responses = deque(_Response(body) for body in bodies)
        self.urls: list[str] = []

    def open(self, request, timeout):
        del timeout
        self.urls.append(request.full_url)
        response = self._responses.popleft()
        response._url = request.full_url
        return response


class _ComponentClock:
    """Place all twelve physical requests inside the collector transaction."""

    def __init__(self) -> None:
        self._tick = 0

    def __call__(self) -> str:
        self._tick += 1
        return ts(BASE + timedelta(seconds=3, milliseconds=self._tick))


def _state_grounded_in_graph(result, graph_registry: dict[str, object]) -> dict:
    closure = sorted(
        graph_registry["evidence_dependency_closure"],
        key=lambda row: row["evidence_digest"],
    )
    selected = closure[:3]
    if len(selected) != 3:
        raise AssertionError("fixture graph must expose at least three evidence rows")
    evidence_refs = [str(row["evidence_digest"]) for row in selected]
    dependency_groups = sorted(
        {
            str(dependency)
            for row in selected
            for dependency in row["dependency_group_ids"]
        }
    )

    values = deepcopy(_kwargs())
    decision_time = str(result.formal_qualification["decision_time"])
    values.update(
        {
            "run_id": result.run_id,
            "cycle_index": result.cycle_index,
            "as_of": decision_time,
        }
    )
    for unknown in values["unknowns"]:
        unknown["dependency_refs"] = dependency_groups

    zone = values["zones"][0]
    zone.update(
        {
            "evidence_refs": evidence_refs,
            "dependency_groups": dependency_groups,
            "touch_count": 2,
            "touch_refs": evidence_refs[:2],
            "reaction_refs": evidence_refs[1:],
            "volume_at_price_refs": [evidence_refs[0]],
            "dwell_time_refs": [evidence_refs[1]],
            "round_number_refs": [evidence_refs[2]],
            "orderbook_flow_refs": [evidence_refs[0]],
            "leverage_refs": [evidence_refs[1]],
            "options_refs": [],
        }
    )
    for hypothesis in values["hypotheses"]:
        hypothesis.update(
            {
                "source_refs": [evidence_refs[0]],
                "supporting_refs": [evidence_refs[1]],
                "opposing_refs": [evidence_refs[2]],
                "dependency_groups": dependency_groups,
                # This fixture proves physical transport chronology, not the
                # mechanism-distinct evidence needed to claim HIGH.  Keep the
                # hypotheses LOW instead of manufacturing independence from
                # whichever three closure rows sort first.
                "subjective_plausibility_tier": "LOW",
            }
        )
    for modifier in values["path_modifiers"]:
        modifier["source_refs"] = evidence_refs[:2]
        modifier["dependency_groups"] = dependency_groups
    values["market_regime_state"]["evidence_refs"] = [evidence_refs[0]]
    values["market_regime_state"]["counter_evidence_refs"] = [evidence_refs[2]]

    values["dependency_clusters"] = [
        {
            "cluster_id": "cluster-long",
            "member_hypothesis_ids": sorted(
                ["action-long", "forecast-absorption", "state-long"]
            ),
            "direction": "LONG",
            "shared_dependency_groups": dependency_groups,
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "cluster-short",
            "member_hypothesis_ids": sorted(
                [
                    "action-short",
                    "forecast-false-break",
                    "forecast-rejection",
                    "state-short",
                ]
            ),
            "direction": "SHORT",
            "shared_dependency_groups": dependency_groups,
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "cluster-neutral",
            "member_hypothesis_ids": ["attribution-neutral"],
            "direction": "NEUTRAL",
            "shared_dependency_groups": dependency_groups,
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
    ]
    return build_v32_dynamic_research_state_v1(**values)


class V32FormalChronologyTests(unittest.TestCase):
    def test_real_transport_collector_graph_and_continuity_share_valid_chronology(
        self,
    ) -> None:
        template = raw_bundle()
        bodies = [str(row["body_utf8"]) for row in template["components"]]
        opener = _Opener(bodies)
        transport = V32OkxPublicBundleTransport(
            clock=_ComponentClock(), opener=opener
        )
        with tempfile.TemporaryDirectory() as directory:
            collector = V32RawFirstOkxPublicBundleCollector(
                transport=transport,
                clock=SequenceClock(),
                store=LocalV32CycleSourceAdmissionStore(Path(directory)),
            )
            result = collector.collect_and_qualify(
                qualification_id="q-v32-formal-chronology",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )

        analysis = result.public_market_analysis_bundle
        pit = result.pit_registry
        decision_time = str(result.formal_qualification["decision_time"])
        projection = build_v32_public_market_graph_projection_v1(analysis)
        graph = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=projection,
            analysis_bundle=analysis,
            decision_time=decision_time,
        )
        verifier = V32InfrastructurePublicEvidenceVerifier()
        availability = build_v32_verified_pit_evidence_availability_registry_v1(
            public_evidence_verifier=verifier,
            public_market_analysis_bundle=analysis,
            pit_evidence_registry=pit,
        )
        state = _state_grounded_in_graph(result, graph)

        response_received_at = str(result.source_capture["response_received_at"])
        completed_at = str(result.formal_qualification["completed_at"])
        self.assertLess(_moment(response_received_at), _moment(completed_at))
        self.assertLessEqual(_moment(completed_at), _moment(decision_time))
        self.assertEqual(response_received_at, pit["as_of"])
        self.assertEqual(response_received_at, availability["as_of"])
        self.assertLess(_moment(pit["as_of"]), _moment(decision_time))
        self.assertLess(_moment(availability["as_of"]), _moment(decision_time))
        self.assertEqual(decision_time, graph["as_of"])
        self.assertEqual(decision_time, state["as_of"])
        self.assertEqual(12, len(opener.urls))

        arguments = {
            "public_evidence_verifier": verifier,
            "current_state": state,
            "durable_previous_state": None,
            "durable_previous_state_digest": None,
            "verified_pit_evidence_registry": pit,
            "verified_pit_evidence_registry_digest": pit[
                PIT_REGISTRY_DIGEST_FIELD
            ],
            "verified_public_market_analysis_bundle": analysis,
            "verified_pit_evidence_availability_registry": availability,
            "verified_pit_evidence_availability_registry_digest": availability[
                PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
            ],
            "durable_previous_pit_evidence_availability_registry": None,
            "durable_previous_pit_evidence_availability_registry_digest": None,
            "verified_graph_dependency_registry": graph,
            "verified_graph_dependency_registry_digest": graph[
                GRAPH_REGISTRY_DIGEST_FIELD
            ],
        }
        receipt = compose_v32_dynamic_state_continuity_v1(**arguments)
        self.assertEqual(
            receipt[RECEIPT_DIGEST_FIELD],
            verify_v32_dynamic_state_continuity_v1(receipt, **arguments),
        )


if __name__ == "__main__":
    unittest.main()
