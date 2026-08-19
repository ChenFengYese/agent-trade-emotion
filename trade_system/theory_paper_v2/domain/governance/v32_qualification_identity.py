"""Exact V3.2 qualification identities and permanent terminal tombstones.

This Domain contract owns run-identity syntax and non-reuse.  It deliberately
contains no filesystem access: failed and expired-terminal identities are
committed facts, so new qualification code never needs to open a historical
runtime before rejecting reuse.
"""

from __future__ import annotations

import re
from typing import Any


class V32QualificationIdentityError(ValueError):
    """A V3.2 target/qualification identity is invalid or permanently retired."""


FAILED_V32_TARGET_RUN_ID = "v32-prospective-btcusdt-20260808t150343z"
FAILED_V32_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260808t150343z"
)
FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260808t220933z"
)
FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260808t220933z"
)
FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260809t010844z"
)
FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260809t010844z"
)
FAILED_V32_FUNDING_TIME_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260809t030358z"
)
FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260809t030358z"
)
FAILED_V32_MATERIALIZATION_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260809t074253z"
)
FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260809t074253z"
)
FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260809t131915z"
)
FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260809t131915z"
)
EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260809t215807z"
)
EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260809t215807z"
)
FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260810t063618z"
)
FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260810t063618z"
)
FAILED_V32_POSTCOMMIT_REGRESSION_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260810t131414z"
)
FAILED_V32_POSTCOMMIT_REGRESSION_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260810t131414z"
)
EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260810t134909z"
)
EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260810t134909z"
)
FAILED_V32_PHASE_A_CHRONOLOGY_TARGET_RUN_ID = (
    "v32-prospective-btcusdt-20260810t151431z"
)
FAILED_V32_PHASE_A_CHRONOLOGY_QUALIFICATION_RUN_ID = (
    "v32-qualification-btcusdt-20260810t151431z"
)
FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE = "QUALIFICATION_PHASE_A"
FAILED_V32_QUALIFICATION_IDENTITY_PAIRS = frozenset(
    {
        (FAILED_V32_QUALIFICATION_RUN_ID, FAILED_V32_TARGET_RUN_ID),
        (
            FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
            FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
            FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
            FAILED_V32_FUNDING_TIME_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
            FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
            FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
            FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_POSTCOMMIT_REGRESSION_QUALIFICATION_RUN_ID,
            FAILED_V32_POSTCOMMIT_REGRESSION_TARGET_RUN_ID,
        ),
        (
            FAILED_V32_PHASE_A_CHRONOLOGY_QUALIFICATION_RUN_ID,
            FAILED_V32_PHASE_A_CHRONOLOGY_TARGET_RUN_ID,
        ),
    }
)
EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS = frozenset(
    {
        (
            EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
            EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
        ),
        (
            EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
            EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID,
        ),
    }
)
HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS = frozenset(
    FAILED_V32_QUALIFICATION_IDENTITY_PAIRS
    | EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS
)
TOMBSTONED_V32_RUN_IDS = frozenset(
    run_id
    for identity_pair in HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS
    for run_id in identity_pair
)

_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")


def validate_v32_run_id_syntax_v1(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or _RUN_ID.fullmatch(value) is None
    ):
        raise V32QualificationIdentityError("V32_QUALIFICATION_RUN_ID_INVALID")
    return value


def validate_v32_active_qualification_identity_v1(
    *, target_run_id: Any, qualification_run_id: Any
) -> tuple[str, str]:
    target = validate_v32_run_id_syntax_v1(target_run_id)
    qualification = validate_v32_run_id_syntax_v1(qualification_run_id)
    if target == qualification:
        raise V32QualificationIdentityError("V32_QUALIFICATION_RUN_ID_INVALID")
    if target in TOMBSTONED_V32_RUN_IDS or qualification in TOMBSTONED_V32_RUN_IDS:
        raise V32QualificationIdentityError("V32_QUALIFICATION_RUN_ID_TOMBSTONED")
    return target, qualification


def is_exact_failed_v32_qualification_preflight_identity_v1(
    *, profile: Any, run_id: Any, target_run_id: Any
) -> bool:
    return (
        profile == FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE
        and (run_id, target_run_id)
        in FAILED_V32_QUALIFICATION_IDENTITY_PAIRS
    )


def is_exact_historical_v32_qualification_preflight_identity_v1(
    *, profile: Any, run_id: Any, target_run_id: Any
) -> bool:
    return (
        profile == FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE
        and (run_id, target_run_id)
        in HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS
    )


__all__ = [
    "FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE",
    "FAILED_V32_QUALIFICATION_IDENTITY_PAIRS",
    "FAILED_V32_QUALIFICATION_RUN_ID",
    "EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID",
    "EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID",
    "EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID",
    "EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID",
    "EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS",
    "FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID",
    "FAILED_V32_FUNDING_TIME_TARGET_RUN_ID",
    "FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID",
    "FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID",
    "FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID",
    "FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID",
    "FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID",
    "FAILED_V32_MATERIALIZATION_TARGET_RUN_ID",
    "FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID",
    "FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID",
    "FAILED_V32_PHASE_A_CHRONOLOGY_QUALIFICATION_RUN_ID",
    "FAILED_V32_PHASE_A_CHRONOLOGY_TARGET_RUN_ID",
    "FAILED_V32_POSTCOMMIT_REGRESSION_QUALIFICATION_RUN_ID",
    "FAILED_V32_POSTCOMMIT_REGRESSION_TARGET_RUN_ID",
    "FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID",
    "FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID",
    "FAILED_V32_TARGET_RUN_ID",
    "HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS",
    "TOMBSTONED_V32_RUN_IDS",
    "V32QualificationIdentityError",
    "is_exact_failed_v32_qualification_preflight_identity_v1",
    "is_exact_historical_v32_qualification_preflight_identity_v1",
    "validate_v32_active_qualification_identity_v1",
    "validate_v32_run_id_syntax_v1",
]
