"""Create the sole immutable ``InputSnapshot`` for a market cycle."""

from __future__ import annotations

from typing import Mapping

from ...domain.market_cycle.contracts import ArtifactRef, CycleRequest, InputSnapshot
from .ports import ClockPort, MarketCaptureRequest, MarketDataPort


class MarketCycleSourceError(ValueError):
    """The public source could not produce an admissible baseline snapshot."""


def capture_input_snapshot(
    request: CycleRequest,
    *,
    market_data: MarketDataPort,
    clock: ClockPort,
) -> InputSnapshot:
    """Capture four core observations and seal their point-in-time boundary."""

    observation = market_data.capture(
        MarketCaptureRequest(
            cycle_id=request.cycle_id,
            venue_id=request.venue_id,
            instrument_id=request.instrument_id,
            contract_type=request.contract_identity,
            requested_at=request.requested_at,
            analysis_profile=request.analysis_profile,
            data_profile=request.data_profile,
        )
    )
    raw_refs = tuple(ArtifactRef.from_dict(item) for item in observation.raw_refs)
    unknown_codes: list[str] = []
    for index, item in enumerate(observation.unknowns):
        if not isinstance(item, Mapping):
            raise MarketCycleSourceError(
                f"MARKET_CYCLE_UNKNOWN_INVALID:{index}"
            )
        code = item.get("code")
        typed_keys_present = any(
            key in item
            for key in ("component_id", "status", "missing_reason", "missing_is_zero")
        )
        if typed_keys_present and (
            not isinstance(item.get("component_id"), str)
            or not item.get("component_id")
            or item.get("status") != "UNKNOWN"
            or not isinstance(item.get("missing_reason"), str)
            or not item.get("missing_reason")
            or item.get("missing_is_zero") is not False
        ):
            raise MarketCycleSourceError(f"MARKET_CYCLE_UNKNOWN_INVALID:{index}")
        if code is None:
            component = item.get("component_id")
            reason = item.get("missing_reason")
            if (
                not isinstance(component, str)
                or not component
                or item.get("status") != "UNKNOWN"
                or not isinstance(reason, str)
                or not reason
                or item.get("missing_is_zero") is not False
            ):
                raise MarketCycleSourceError(
                    f"MARKET_CYCLE_UNKNOWN_INVALID:{index}"
                )
            code = f"{component}:{reason}"
        if not isinstance(code, str) or not code:
            raise MarketCycleSourceError(f"MARKET_CYCLE_UNKNOWN_CODE_INVALID:{index}")
        unknown_codes.append(code)
    return InputSnapshot.seal(
        request,
        snapshot_id=f"{request.cycle_id}.input",
        source_cutoff_at=observation.cutoff_at,
        decision_at=observation.captured_at,
        sealed_at=clock(),
        core_observations=observation.core_observations,
        optional_observations=observation.optional_observations,
        unknowns=tuple(unknown_codes),
        raw_refs=raw_refs,
        source_health=observation.source_health,
    )


__all__ = ["MarketCycleSourceError", "capture_input_snapshot"]
