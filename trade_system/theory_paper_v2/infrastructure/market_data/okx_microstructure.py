"""Pure parsers for bounded OKX public book and trade observations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping

from ...domain.contracts.canonical import canonical_decimal


PARSER_VERSION = "okx-public-microstructure-v1"
ORDER_BOOK_DEPTH_LIMIT = 20
RECENT_TRADES_LIMIT = 100
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


class OkxMicrostructureError(ValueError):
    """An optional provider response cannot be used as an observation."""


class OkxMicrostructureIntegrityError(OkxMicrostructureError):
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
        raise OkxMicrostructureError(code) from exc
    if (
        not isinstance(root, Mapping)
        or set(root) not in ({"code", "data"}, {"code", "msg", "data"})
        or root.get("code") != "0"
        or "msg" in root and root.get("msg") != ""
        or not isinstance(root.get("data"), list)
    ):
        raise OkxMicrostructureError(code)
    return list(root["data"])


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxMicrostructureIntegrityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxMicrostructureIntegrityError(code) from exc
    if parsed.tzinfo is None:
        raise OkxMicrostructureIntegrityError(code)
    return parsed.astimezone(UTC)


def _provider_time(value: object, *, available_at: str, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 13
        or not value.isascii()
        or not value.isdigit()
        or int(value) <= 0
    ):
        raise OkxMicrostructureError(code)
    provider = datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    available = _moment(available_at, code=f"{code}:AVAILABLE_AT_INVALID")
    if provider > available + timedelta(seconds=5):
        raise OkxMicrostructureIntegrityError(f"{code}:FUTURE_DATUM")
    return provider.isoformat().replace("+00:00", "Z")


def _decimal(value: object, *, code: str, positive: bool = False) -> str:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise OkxMicrostructureError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OkxMicrostructureError(code) from exc
    if not parsed.is_finite() or parsed < 0 or positive and parsed <= 0:
        raise OkxMicrostructureError(code)
    return canonical_decimal(parsed)


def _integer_text(value: object, *, code: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and _INTEGER.fullmatch(value):
        return value
    raise OkxMicrostructureError(code)


def _book_side(value: object, *, side: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > ORDER_BOOK_DEPTH_LIMIT:
        raise OkxMicrostructureError("OKX_BOOK_DEPTH_INVALID")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 4:
            raise OkxMicrostructureError(f"OKX_BOOK_{side}_ROW_INVALID:{index}")
        if item[2] != "0":
            raise OkxMicrostructureError(f"OKX_BOOK_{side}_DEPRECATED_FIELD_INVALID:{index}")
        rows.append(
            {
                "price": _decimal(
                    item[0], code=f"OKX_BOOK_{side}_PRICE_INVALID:{index}", positive=True
                ),
                "size_contracts": _decimal(
                    item[1], code=f"OKX_BOOK_{side}_SIZE_INVALID:{index}"
                ),
                "order_count": _integer_text(
                    item[3], code=f"OKX_BOOK_{side}_COUNT_INVALID:{index}"
                ),
            }
        )
    return rows


def parse_okx_order_book(
    *, raw: bytes, instrument_id: str, available_at: str
) -> dict[str, object]:
    """Return one exact depth-20 snapshot from already sealed response bytes."""

    rows = _rows(raw, code="OKX_BOOK_RESPONSE_INVALID")
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise OkxMicrostructureError("OKX_BOOK_RESPONSE_AMBIGUOUS")
    row = rows[0]
    required = {"asks", "bids", "ts"}
    allowed = required | {"checksum", "seqId", "prevSeqId"}
    if not required.issubset(row) or not set(row).issubset(allowed):
        raise OkxMicrostructureError("OKX_BOOK_DATUM_SCHEMA_INVALID")
    asks = _book_side(row["asks"], side="ASK")
    bids = _book_side(row["bids"], side="BID")
    if not asks or not bids:
        raise OkxMicrostructureError("OKX_BOOK_TWO_SIDED_DEPTH_MISSING")
    result: dict[str, object] = {
        "instrument_id": instrument_id,
        "provider_as_of": _provider_time(
            row["ts"], available_at=available_at, code="OKX_BOOK_PROVIDER_TIME_INVALID"
        ),
        "depth_limit": ORDER_BOOK_DEPTH_LIMIT,
        "asks": asks,
        "bids": bids,
    }
    for provider_name, output_name in (
        ("checksum", "checksum"),
        ("seqId", "seq_id"),
        ("prevSeqId", "previous_seq_id"),
    ):
        if provider_name in row:
            result[output_name] = _integer_text(
                row[provider_name], code=f"OKX_BOOK_{provider_name.upper()}_INVALID"
            )
    return result


def parse_okx_recent_trades(
    *, raw: bytes, instrument_id: str, available_at: str
) -> list[dict[str, str]]:
    """Return at most 100 exact recent public trades from sealed bytes."""

    rows = _rows(raw, code="OKX_TRADES_RESPONSE_INVALID")
    if not rows or len(rows) > RECENT_TRADES_LIMIT:
        raise OkxMicrostructureError("OKX_TRADES_COUNT_INVALID")
    parsed: list[dict[str, str]] = []
    trade_ids: set[str] = set()
    required = {"instId", "tradeId", "px", "sz", "side", "ts"}
    allowed = required | {"count", "source"}
    for index, row in enumerate(rows):
        if (
            not isinstance(row, Mapping)
            or not required.issubset(row)
            or not set(row).issubset(allowed)
        ):
            raise OkxMicrostructureError(f"OKX_TRADE_SCHEMA_INVALID:{index}")
        if row.get("instId") != instrument_id:
            raise OkxMicrostructureIntegrityError(
                f"OKX_TRADE_INSTRUMENT_MISMATCH:{index}"
            )
        trade_id = _integer_text(row["tradeId"], code=f"OKX_TRADE_ID_INVALID:{index}")
        if trade_id in trade_ids:
            raise OkxMicrostructureError(f"OKX_TRADE_ID_DUPLICATE:{index}")
        trade_ids.add(trade_id)
        if row.get("side") not in {"buy", "sell"}:
            raise OkxMicrostructureError(f"OKX_TRADE_SIDE_INVALID:{index}")
        item = {
            "instrument_id": instrument_id,
            "trade_id": trade_id,
            "price": _decimal(
                row["px"], code=f"OKX_TRADE_PRICE_INVALID:{index}", positive=True
            ),
            "size_contracts": _decimal(
                row["sz"], code=f"OKX_TRADE_SIZE_INVALID:{index}"
            ),
            "taker_side": str(row["side"]),
            "provider_as_of": _provider_time(
                row["ts"],
                available_at=available_at,
                code=f"OKX_TRADE_PROVIDER_TIME_INVALID:{index}",
            ),
        }
        if "count" in row:
            item["count"] = _integer_text(
                row["count"], code=f"OKX_TRADE_COUNT_INVALID:{index}"
            )
        if "source" in row:
            item["source"] = _integer_text(
                row["source"], code=f"OKX_TRADE_SOURCE_INVALID:{index}"
            )
        parsed.append(item)
    return parsed


__all__ = [
    "ORDER_BOOK_DEPTH_LIMIT",
    "PARSER_VERSION",
    "RECENT_TRADES_LIMIT",
    "OkxMicrostructureError",
    "OkxMicrostructureIntegrityError",
    "parse_okx_order_book",
    "parse_okx_recent_trades",
]
