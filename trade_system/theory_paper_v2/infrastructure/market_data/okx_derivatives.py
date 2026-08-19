"""Pure parsers for bounded OKX public OI and funding observations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping

from ...domain.contracts.canonical import canonical_decimal


PARSER_VERSION = "okx-public-derivatives-v1"
FUNDING_HISTORY_LIMIT = 10
_UNSIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_SIGNED_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class OkxDerivativesError(ValueError):
    """An optional provider response cannot be used as an observation."""


class OkxDerivativesIntegrityError(OkxDerivativesError):
    """Provider identity or point-in-time evidence is unsafe to downgrade."""


def _rows(raw: bytes, *, code: str) -> list[Any]:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_number(value):
        raise ValueError(f"unsupported JSON number: {value}")

    try:
        root = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_int=str,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise OkxDerivativesError(code) from exc
    if (
        not isinstance(root, Mapping)
        or set(root) not in ({"code", "data"}, {"code", "msg", "data"})
        or root.get("code") != "0"
        or "msg" in root and root.get("msg") != ""
        or not isinstance(root.get("data"), list)
    ):
        raise OkxDerivativesError(code)
    return list(root["data"])


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxDerivativesIntegrityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxDerivativesIntegrityError(code) from exc
    if parsed.tzinfo is None:
        raise OkxDerivativesIntegrityError(code)
    return parsed.astimezone(UTC)


def _provider_time(value: object, *, available_at: str, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 13
        or not value.isascii()
        or not value.isdigit()
        or int(value) <= 0
    ):
        raise OkxDerivativesError(code)
    provider = datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    available = _moment(available_at, code=f"{code}:AVAILABLE_AT_INVALID")
    if provider > available + timedelta(seconds=5):
        raise OkxDerivativesIntegrityError(f"{code}:FUTURE_DATUM")
    return provider.isoformat().replace("+00:00", "Z")


def _decimal(
    value: object, *, code: str, signed: bool = False, positive: bool = False
) -> str:
    pattern = _SIGNED_DECIMAL if signed else _UNSIGNED_DECIMAL
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise OkxDerivativesError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OkxDerivativesError(code) from exc
    if not parsed.is_finite() or not signed and parsed < 0 or positive and parsed <= 0:
        raise OkxDerivativesError(code)
    return canonical_decimal(parsed)


def parse_okx_open_interest(
    *, raw: bytes, instrument_id: str, available_at: str
) -> dict[str, str]:
    """Return one exact SWAP open-interest observation from sealed bytes."""

    rows = _rows(raw, code="OKX_OPEN_INTEREST_RESPONSE_INVALID")
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise OkxDerivativesError("OKX_OPEN_INTEREST_RESPONSE_AMBIGUOUS")
    row = rows[0]
    required = {"instType", "instId", "oi", "oiCcy", "ts"}
    allowed = required | {"oiUsd"}
    if not required.issubset(row) or not set(row).issubset(allowed):
        raise OkxDerivativesError("OKX_OPEN_INTEREST_SCHEMA_INVALID")
    if row.get("instType") != "SWAP" or row.get("instId") != instrument_id:
        raise OkxDerivativesIntegrityError("OKX_OPEN_INTEREST_IDENTITY_MISMATCH")
    result = {
        "instrument_id": instrument_id,
        "contract_type": "SWAP",
        "open_interest_contracts": _decimal(
            row["oi"], code="OKX_OPEN_INTEREST_VALUE_INVALID"
        ),
        "open_interest_currency": _decimal(
            row["oiCcy"], code="OKX_OPEN_INTEREST_CURRENCY_VALUE_INVALID"
        ),
        "provider_as_of": _provider_time(
            row["ts"],
            available_at=available_at,
            code="OKX_OPEN_INTEREST_PROVIDER_TIME_INVALID",
        ),
    }
    if "oiUsd" in row:
        result["open_interest_usd"] = _decimal(
            row["oiUsd"], code="OKX_OPEN_INTEREST_USD_INVALID"
        )
    return result


def parse_okx_funding_rate_history(
    *, raw: bytes, instrument_id: str, available_at: str
) -> list[dict[str, str]]:
    """Return up to ten realized public funding records from sealed bytes."""

    rows = _rows(raw, code="OKX_FUNDING_HISTORY_RESPONSE_INVALID")
    if not rows or len(rows) > FUNDING_HISTORY_LIMIT:
        raise OkxDerivativesError("OKX_FUNDING_HISTORY_COUNT_INVALID")
    parsed: list[dict[str, str]] = []
    funding_times: set[str] = set()
    required = {"instId", "fundingRate", "fundingTime"}
    allowed = required | {"formulaType", "instType", "method", "realizedRate"}
    for index, row in enumerate(rows):
        if (
            not isinstance(row, Mapping)
            or not required.issubset(row)
            or not set(row).issubset(allowed)
        ):
            raise OkxDerivativesError(f"OKX_FUNDING_HISTORY_SCHEMA_INVALID:{index}")
        if row.get("instId") != instrument_id or (
            "instType" in row and row.get("instType") != "SWAP"
        ):
            raise OkxDerivativesIntegrityError(
                f"OKX_FUNDING_HISTORY_IDENTITY_MISMATCH:{index}"
            )
        provider_as_of = _provider_time(
            row["fundingTime"],
            available_at=available_at,
            code=f"OKX_FUNDING_HISTORY_TIME_INVALID:{index}",
        )
        if provider_as_of in funding_times:
            raise OkxDerivativesError(f"OKX_FUNDING_HISTORY_TIME_DUPLICATE:{index}")
        funding_times.add(provider_as_of)
        item = {
            "instrument_id": instrument_id,
            "funding_rate": _decimal(
                row["fundingRate"],
                code=f"OKX_FUNDING_RATE_INVALID:{index}",
                signed=True,
            ),
            "provider_as_of": provider_as_of,
        }
        for name in ("formulaType", "method"):
            if name in row:
                if not isinstance(row[name], str) or not row[name]:
                    raise OkxDerivativesError(
                        f"OKX_FUNDING_{name.upper()}_INVALID:{index}"
                    )
                item[name] = row[name]
        if "realizedRate" in row:
            item["realized_rate"] = _decimal(
                row["realizedRate"],
                code=f"OKX_FUNDING_REALIZED_RATE_INVALID:{index}",
                signed=True,
            )
        parsed.append(item)
    return parsed


__all__ = [
    "FUNDING_HISTORY_LIMIT",
    "PARSER_VERSION",
    "OkxDerivativesError",
    "OkxDerivativesIntegrityError",
    "parse_okx_funding_rate_history",
    "parse_okx_open_interest",
]
