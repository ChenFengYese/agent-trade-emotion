"""Production UTC wall clock plus monotonic duration source."""

from __future__ import annotations

from datetime import UTC, datetime
import time


class SystemUTCMonotonicClock:
    """Small non-injectable production clock; tests use the ClockPort directly."""

    __slots__ = ()

    def __call__(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def monotonic_ns(self) -> int:
        value = time.monotonic_ns()
        if type(value) is not int or value < 0:
            raise RuntimeError("SYSTEM_MONOTONIC_CLOCK_INVALID")
        return value


__all__ = ["SystemUTCMonotonicClock"]
