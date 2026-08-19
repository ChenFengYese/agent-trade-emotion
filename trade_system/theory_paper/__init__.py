"""Experimental, public-data-only theory-practice paper runtime.

This package never connects to an account or submits an exchange order.  It
turns public point-in-time market observations into auditable analysis packets,
accepts a separately reasoned agent decision, and applies that decision to a
local paper portfolio.
"""

from .experiment import (
    finalize_experiment,
    initialize_experiment,
    run_hourly_cycle,
    run_review,
    status_report,
    submit_agent_decision,
)

__all__ = [
    "finalize_experiment",
    "initialize_experiment",
    "run_hourly_cycle",
    "run_review",
    "status_report",
    "submit_agent_decision",
]
