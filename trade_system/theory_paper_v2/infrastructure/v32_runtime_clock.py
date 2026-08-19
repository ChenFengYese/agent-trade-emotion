"""Production system-clock adapter for the local V3.2 prospective runtime.

The factory deliberately accepts no injected wall-clock source.  Tests remain
free to pass a deterministic callable directly to the application router, but
production composition must construct this adapter internally.  UTC is used
for durable timestamps; monotonic time is used only for elapsed durations and
is never serialized as a cross-process authority value.
"""

from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any


class V32RuntimeClockError(ValueError):
    """The local system clock failed an invariant."""


class SystemUTCMonotonicClockV1:
    """Read operating-system UTC and monotonic duration without injection."""

    __slots__ = ()

    adapter_id = "V32_SYSTEM_UTC_MONOTONIC_CLOCK_V1"
    wall_clock_source = "OPERATING_SYSTEM_UTC"
    duration_clock_source = "OPERATING_SYSTEM_MONOTONIC_NS"
    caller_wall_clock_injection_allowed = False

    def __call__(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def monotonic_ns(self) -> int:
        value = time.monotonic_ns()
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise V32RuntimeClockError("V32_SYSTEM_MONOTONIC_CLOCK_INVALID")
        return value

    def elapsed_milliseconds(self, started_at_monotonic_ns: Any) -> int:
        if (
            isinstance(started_at_monotonic_ns, bool)
            or not isinstance(started_at_monotonic_ns, int)
            or started_at_monotonic_ns < 0
        ):
            raise V32RuntimeClockError("V32_SYSTEM_MONOTONIC_START_INVALID")
        elapsed_ns = self.monotonic_ns() - started_at_monotonic_ns
        if elapsed_ns < 0:
            raise V32RuntimeClockError("V32_SYSTEM_MONOTONIC_ROLLBACK")
        return elapsed_ns // 1_000_000


def build_v32_system_clock_v1() -> SystemUTCMonotonicClockV1:
    """Construct the sole production clock; no caller clock is accepted."""

    return SystemUTCMonotonicClockV1()


__all__ = [
    "SystemUTCMonotonicClockV1",
    "V32RuntimeClockError",
    "build_v32_system_clock_v1",
]
