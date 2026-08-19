"""Bounded, non-authoritative summaries for sealed provider payloads."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET


class NormalizeError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NormalizeError("V332_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizeError("V332_JSON_INVALID") from exc


def _bounded_fields(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return sorted(str(key) for key in value.keys())[:80]
    return []


def _first_records(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [record for record in value[:3] if isinstance(record, Mapping)]
    return []


def _timestamp_candidates(records: Iterable[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    names = (
        "ts",
        "time",
        "timestamp",
        "date",
        "period",
        "realtime_start",
        "observation_date",
        "createdAt",
        "indexedAt",
        "seendate",
    )
    for record in records:
        for name in names:
            value = record.get(name)
            if isinstance(value, (str, int, float)):
                values.append(str(value))
    return values[:20]


def _safe_preview(record: Mapping[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key in sorted(record):
        value = record[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = value
            if isinstance(text, str) and len(text) > 240:
                text = text[:237] + "..."
            preview[str(key)] = text
        if len(preview) >= 16:
            break
    return preview


_OKX_ARRAY_FIELDS = {
    "okx.candles_15m": ("ts", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "confirm"),
    "okx.candles_1h": ("ts", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "confirm"),
    "okx.candles_4h": ("ts", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "confirm"),
    "okx.candles_1d": ("ts", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "confirm"),
    "okx.taker_volume": ("ts", "buy_volume", "sell_volume"),
    "okx.long_short_contract": ("ts", "long_short_ratio"),
    "okx.long_short_currency": ("ts", "long_short_ratio"),
}


def _safe_array_preview(row: list[Any], fields: tuple[str, ...]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for index, value in enumerate(row[: len(fields)]):
        if isinstance(value, (str, int, float, bool)) or value is None:
            preview[fields[index]] = value
    return preview


def _normalize_okx(source_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_OKX_OBJECT_REQUIRED")
    data = value.get("data")
    records = data if isinstance(data, list) else []
    mapping_records = _first_records(records)
    array_fields = _OKX_ARRAY_FIELDS.get(source_id, ())
    array_records = [row for row in records[:3] if isinstance(row, list)]
    timestamp_candidates = _timestamp_candidates(mapping_records)
    if array_records and array_fields and array_records[0]:
        timestamp_candidates = [str(row[0]) for row in array_records if row][:20]
    previews: list[Mapping[str, Any]] = [
        _safe_preview(record) for record in mapping_records
    ]
    if array_fields:
        previews.extend(_safe_array_preview(row, array_fields) for row in array_records)
    return {
        "format": "json",
        "provider_code": value.get("code"),
        "provider_message": value.get("msg"),
        "record_count": len(records),
        "record_fields": (
            _bounded_fields(records[0])
            if records and isinstance(records[0], Mapping)
            else list(array_fields)
        ),
        "record_shape": (
            len(records[0]) if records and isinstance(records[0], list) else None
        ),
        "provider_time_candidates": timestamp_candidates,
        "preview": previews[:3],
    }


def _normalize_bls(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_BLS_OBJECT_REQUIRED")
    results = value.get("Results")
    series = results.get("series", []) if isinstance(results, Mapping) else []
    summaries = []
    total = 0
    for item in series if isinstance(series, list) else []:
        if not isinstance(item, Mapping):
            continue
        observations = item.get("data", [])
        observations = observations if isinstance(observations, list) else []
        total += len(observations)
        summaries.append(
            {
                "seriesID": item.get("seriesID"),
                "observation_count": len(observations),
                "latest": _safe_preview(observations[0]) if observations else None,
            }
        )
    return {
        "format": "json",
        "provider_status": value.get("status"),
        "series_count": len(summaries),
        "record_count": total,
        "series": summaries[:20],
    }


def _normalize_gdelt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_GDELT_OBJECT_REQUIRED")
    articles = value.get("articles", [])
    articles = articles if isinstance(articles, list) else []
    previews = []
    for article in articles[:10]:
        if not isinstance(article, Mapping):
            continue
        previews.append(
            {
                key: article.get(key)
                for key in (
                    "title",
                    "url",
                    "domain",
                    "seendate",
                    "language",
                    "sourcecountry",
                )
                if key in article
            }
        )
    return {
        "format": "json",
        "record_count": len(articles),
        "provider_time_candidates": _timestamp_candidates(_first_records(articles)),
        "preview": previews,
        "claim_ceiling": "MEDIA_DISCOVERY_SAMPLE_NOT_EVENT_OR_SENTIMENT_TRUTH",
    }


def _normalize_coinmetrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_COINMETRICS_OBJECT_REQUIRED")
    data = value.get("data", [])
    records = data if isinstance(data, list) else []
    return {
        "format": "json",
        "record_count": len(records),
        "record_fields": _bounded_fields(records[0]) if records else [],
        "provider_time_candidates": _timestamp_candidates(_first_records(records)),
        "preview": [_safe_preview(record) for record in records[-3:] if isinstance(record, Mapping)],
        "next_page_token_present": bool(value.get("next_page_token")),
    }


def _normalize_bluesky(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_BLUESKY_OBJECT_REQUIRED")
    posts = value.get("posts", [])
    posts = posts if isinstance(posts, list) else []
    preview = []
    for post in posts[:10]:
        if not isinstance(post, Mapping):
            continue
        author = post.get("author")
        record = post.get("record")
        preview.append(
            {
                "uri": post.get("uri"),
                "cid": post.get("cid"),
                "author_did": author.get("did") if isinstance(author, Mapping) else None,
                "author_handle": author.get("handle") if isinstance(author, Mapping) else None,
                "createdAt": record.get("createdAt") if isinstance(record, Mapping) else None,
                "indexedAt": post.get("indexedAt"),
            }
        )
    return {
        "format": "json",
        "record_count": len(posts),
        "preview": preview,
        "claim_ceiling": "PUBLIC_APPVIEW_SAMPLE_NOT_TOTAL_SOCIAL_SENTIMENT",
    }


def _normalize_eia_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_EIA_MANIFEST_OBJECT_REQUIRED")
    datasets = value.get("dataset")
    if not isinstance(datasets, Mapping):
        raise NormalizeError("V332_EIA_MANIFEST_DATASET_REQUIRED")
    preview = []
    for identifier in sorted(datasets)[:40]:
        item = datasets[identifier]
        if not isinstance(item, Mapping):
            continue
        preview.append(
            {
                "identifier": identifier,
                "name": item.get("name"),
                "last_updated": item.get("last_updated"),
                "accessURL": item.get("accessURL"),
                "temporal": item.get("temporal"),
            }
        )
    return {
        "format": "json",
        "record_count": len(datasets),
        "record_fields": ["identifier", "name", "last_updated", "accessURL", "temporal"],
        "preview": preview,
        "claim_ceiling": "PUBLIC_BULK_CATALOG_NOT_TARGETED_SERIES_OBSERVATIONS",
    }


def _normalize_youtube(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_YOUTUBE_OBJECT_REQUIRED")
    items = value.get("items", [])
    items = items if isinstance(items, list) else []
    error = value.get("error")
    error = error if isinstance(error, Mapping) else {}
    details = error.get("errors", [])
    details = details if isinstance(details, list) else []
    reasons = [
        str(item["reason"])
        for item in details
        if isinstance(item, Mapping) and item.get("reason")
    ][:20]
    preview = []
    for item in items[:10]:
        if not isinstance(item, Mapping):
            continue
        identifier = item.get("id")
        snippet = item.get("snippet")
        preview.append(
            {
                "video_id": (
                    identifier.get("videoId")
                    if isinstance(identifier, Mapping)
                    else None
                ),
                "published_at": (
                    snippet.get("publishedAt")
                    if isinstance(snippet, Mapping)
                    else None
                ),
                "channel_id": (
                    snippet.get("channelId")
                    if isinstance(snippet, Mapping)
                    else None
                ),
                "title": (
                    str(snippet.get("title"))[:240]
                    if isinstance(snippet, Mapping) and snippet.get("title")
                    else None
                ),
            }
        )
    message = error.get("message")
    return {
        "format": "json",
        "record_count": len(items),
        "record_fields": ["video_id", "published_at", "channel_id", "title"],
        "preview": preview,
        "provider_error_code": error.get("code"),
        "provider_error_status": error.get("status"),
        "provider_error_reasons": reasons,
        "provider_message": str(message)[:500] if message else None,
        "claim_ceiling": "BOUNDED_PUBLIC_VIDEO_SEARCH_SAMPLE_NOT_TOTAL_SENTIMENT",
    }


def _normalize_alphavantage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizeError("V332_ALPHAVANTAGE_OBJECT_REQUIRED")
    series = value.get("Time Series (Daily)")
    series = series if isinstance(series, Mapping) else {}
    dates = sorted((str(key) for key in series), reverse=True)
    preview = []
    record_fields: list[str] = []
    for date in dates[:3]:
        record = series.get(date)
        if not isinstance(record, Mapping):
            continue
        if not record_fields:
            record_fields = _bounded_fields(record)
        preview.append({"date": date, **_safe_preview(record)})
    error_field = next(
        (
            name
            for name in ("Error Message", "Information", "Note")
            if value.get(name)
        ),
        None,
    )
    error_message = value.get(error_field) if error_field else None
    metadata = value.get("Meta Data")
    return {
        "format": "json",
        "record_count": len(series),
        "record_fields": ["date", *record_fields],
        "provider_time_candidates": dates[:20],
        "preview": preview,
        "metadata_fields": _bounded_fields(metadata),
        "provider_error_field": error_field,
        "provider_message": (
            str(error_message)[:500] if error_message is not None else None
        ),
    }


def _deep_record_list(value: Any, *, depth: int = 0) -> list[Mapping[str, Any]]:
    """Find a bounded nested record list without claiming a provider schema."""

    if depth > 4:
        return []
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, Mapping)]
        if records:
            return records
        for item in value[:20]:
            found = _deep_record_list(item, depth=depth + 1)
            if found:
                return found
    if isinstance(value, Mapping):
        for key in sorted(value):
            found = _deep_record_list(value[key], depth=depth + 1)
            if found:
                return found
    return []


def _normalize_json(source_id: str, raw: bytes) -> dict[str, Any]:
    value = _json(raw)
    if source_id.startswith("okx."):
        return _normalize_okx(source_id, value)
    if source_id == "bls.labor_snapshot":
        return _normalize_bls(value)
    if source_id == "gdelt.bitcoin_news":
        return _normalize_gdelt(value)
    if source_id == "coinmetrics.btc_daily":
        return _normalize_coinmetrics(value)
    if source_id == "bluesky.search_posts":
        return _normalize_bluesky(value)
    if source_id == "eia.bulk_manifest":
        return _normalize_eia_manifest(value)
    if source_id == "youtube.search":
        return _normalize_youtube(value)
    if source_id == "alphavantage.daily":
        return _normalize_alphavantage(value)
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, Mapping)]
        return {
            "format": "json",
            "record_count": len(value),
            "record_fields": _bounded_fields(records[0]) if records else [],
            "provider_time_candidates": _timestamp_candidates(records[:3]),
            "preview": [_safe_preview(record) for record in records[:3]],
        }
    if isinstance(value, Mapping):
        candidates: list[Mapping[str, Any]] = []
        for key in ("data", "results", "observations", "chains", "protocols"):
            child = value.get(key)
            if isinstance(child, list):
                candidates = [item for item in child if isinstance(item, Mapping)]
                break
        if not candidates:
            candidates = _deep_record_list(value)
        return {
            "format": "json",
            "top_level_fields": _bounded_fields(value),
            "record_count": len(candidates),
            "record_fields": _bounded_fields(candidates[0]) if candidates else [],
            "provider_time_candidates": _timestamp_candidates(candidates[:3]),
            "preview": [_safe_preview(record) for record in candidates[:3]],
        }
    return {"format": "json", "value_type": type(value).__name__}


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise NormalizeError("V332_TEXT_DECODE_FAILED")


def _normalize_csv(source_id: str, raw: bytes) -> dict[str, Any]:
    text = _decode_text(raw)
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    headers = list(reader.fieldnames or [])
    result: dict[str, Any] = {
        "format": "csv",
        "record_count": len(rows),
        "record_fields": headers[:120],
        "preview": [_safe_preview(row) for row in rows[:3]],
    }
    if source_id == "cftc.cot_current":
        selected = []
        for row in rows:
            code = str(
                row.get("CFTC_Contract_Market_Code")
                or row.get("CFTC Contract Market Code")
                or row.get("CFTC_Market_Code")
                or ""
            ).strip()
            if code in {"133741", "133742"}:
                selected.append(_safe_preview(row))
        result["bitcoin_contract_record_count"] = len(selected)
        result["bitcoin_contracts"] = selected[:8]
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_xml(raw: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise NormalizeError("V332_XML_INVALID") from exc
    items = [element for element in root.iter() if _local_name(element.tag) in {"item", "entry", "properties"}]
    previews = []
    for item in items[:10]:
        preview: dict[str, Any] = {}
        for child in list(item):
            name = _local_name(child.tag)
            text = (child.text or "").strip()
            if text and name in {"title", "link", "pubDate", "updated", "date", "NEW_DATE", "BC_10YEAR"}:
                preview[name] = text[:500]
        if preview:
            previews.append(preview)
    return {
        "format": "xml",
        "root": _local_name(root.tag),
        "record_count": len(items),
        "preview": previews,
    }


def _normalize_text(source_id: str, raw: bytes) -> dict[str, Any]:
    text = _decode_text(raw)
    lines = text.splitlines()
    matches = [line.strip() for line in lines if "133741" in line or "133742" in line]
    return {
        "format": "text",
        "line_count": len(lines),
        "bitcoin_contract_matches": matches[:20] if source_id.startswith("cftc.") else [],
        "preview": lines[:5],
    }


def normalize_payload(
    *, source_id: str, raw: bytes, content_type: str | None
) -> Mapping[str, Any]:
    if not raw:
        return {"format": "empty", "record_count": 0}
    lowered = (content_type or "").lower()
    stripped = raw.lstrip()
    if "json" in lowered or stripped[:1] in {b"{", b"["}:
        return _normalize_json(source_id, raw)
    if "csv" in lowered or source_id in {
        "cboe.vix_daily",
        "ecb.usd_eur_daily",
        "cftc.cot_current",
        "google_trends.manual_csv",
        "btc_etf.issuer_holdings_manual",
    }:
        try:
            return _normalize_csv(source_id, raw)
        except (csv.Error, NormalizeError):
            if "csv" in lowered:
                raise
    if "xml" in lowered or "rss" in lowered or stripped.startswith(b"<?xml") or stripped.startswith(b"<rss") or stripped.startswith(b"<feed"):
        return _normalize_xml(raw)
    return _normalize_text(source_id, raw)


__all__ = ["NormalizeError", "normalize_payload"]
