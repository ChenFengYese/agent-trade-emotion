"""Source discovery and raw-first capture use cases."""

from __future__ import annotations

from datetime import UTC, datetime
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, Mapping

from .ports import (
    CatalogPort,
    ClockPort,
    RawStorePort,
    TransportPort,
    TransportResponse,
)
from ..domain.contracts import (
    AccessMode,
    CaptureResult,
    CaptureStatus,
    SourceDefinition,
    TransportKind,
    source_readiness,
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _canonical(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("V332_CLOCK_NAIVE")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _terminal_without_capture(
    *,
    definition: SourceDefinition,
    status: CaptureStatus,
    reason: str,
    captured_at: str,
) -> CaptureResult:
    return CaptureResult(
        source_id=definition.source_id,
        status=status,
        capture_id=None,
        captured_at=captured_at,
        available_at=None,
        raw_ref=None,
        observation_path=None,
        reason=reason,
        summary={"claim_ceiling": definition.claim_ceiling},
    )


def _provider_failure(source_id: str, summary: Mapping[str, Any]) -> str | None:
    if source_id.startswith("okx.") and summary.get("format") != "v332_websocket_message_container":
        code = summary.get("provider_code")
        if code not in {0, "0"}:
            return f"OKX_PROVIDER_CODE:{code}"
    if source_id == "bls.labor_snapshot":
        status = summary.get("provider_status")
        if status not in {"REQUEST_SUCCEEDED", "REQUEST_SUCCEEDED_WITH_WARNINGS"}:
            return f"BLS_PROVIDER_STATUS:{status}"
    if source_id == "youtube.search" and summary.get("provider_error_code"):
        return f"YOUTUBE_PROVIDER_ERROR:{summary['provider_error_code']}"
    if source_id == "alphavantage.daily":
        error_field = summary.get("provider_error_field")
        if error_field:
            return f"ALPHAVANTAGE_PROVIDER_ERROR:{error_field}"
        if not summary.get("record_count"):
            return "ALPHAVANTAGE_TIME_SERIES_MISSING"
    return None


class ExternalDataService:
    """The only application owner of finite V3.3.2 source attempts."""

    def __init__(
        self,
        *,
        catalog: CatalogPort,
        transport: TransportPort,
        store: RawStorePort,
        clock: ClockPort | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._catalog = catalog
        self._transport = transport
        self._store = store
        self._clock = clock or SystemClock()
        self._environment = dict(os.environ if environment is None else environment)

    def catalog(self) -> tuple[Mapping[str, Any], ...]:
        result = []
        for source in self._catalog.list():
            definition = source.definition
            status, reason = source_readiness(
                definition,
                environment=self._environment,
                parameters={},
            )
            item = definition.to_dict()
            item["readiness"] = "READY" if status is None else status.value
            item["readiness_reason"] = reason
            result.append(item)
        return tuple(result)

    def collect(
        self,
        source_id: str,
        *,
        parameters: Mapping[str, str] | None = None,
    ) -> CaptureResult:
        parameters = dict(parameters or {})
        source = self._catalog.get(source_id)
        definition = source.definition
        now = self._clock.now()
        captured_at = _canonical(now)
        blocked, reason = source_readiness(
            definition,
            environment=self._environment,
            parameters=parameters,
        )
        if blocked is not None:
            return _terminal_without_capture(
                definition=definition,
                status=blocked,
                reason=reason or "SOURCE_NOT_READY",
                captured_at=captured_at,
            )
        try:
            request = source.build_request(
                parameters=parameters,
                environment=self._environment,
                now=now,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return _terminal_without_capture(
                definition=definition,
                status=CaptureStatus.CAPTURE_FAILED,
                reason=str(exc) or "REQUEST_BUILD_FAILED",
                captured_at=captured_at,
            )

        response = self._transport.execute(request)
        reference = self._store.seal_transport(
            definition=definition,
            request=request,
            response=response,
        )
        raw = self._store.load_raw(reference)
        available_at = response.response_received_at
        status = CaptureStatus.OBSERVED_RAW
        failure = response.error_code
        summary: Mapping[str, Any]
        try:
            summary = source.normalize(body=raw, response=response)
        except (TypeError, ValueError) as exc:
            summary = {
                "format": "unparsed",
                "normalization_error": str(exc) or type(exc).__name__,
            }
            failure = failure or "V332_NORMALIZATION_FAILED"
        if response.protocol == "HTTP":
            if response.status_code is None or not 200 <= response.status_code < 300:
                failure = failure or "V332_HTTP_NON_SUCCESS"
            elif not raw:
                status = CaptureStatus.OBSERVED_EMPTY
        elif response.protocol == "WEBSOCKET":
            if response.status_code != 101:
                failure = failure or "V332_WS_NOT_UPGRADED"
            elif summary.get("message_count") == 0:
                status = CaptureStatus.OBSERVED_EMPTY
        failure = failure or _provider_failure(source_id, summary)
        if failure:
            status = CaptureStatus.CAPTURE_FAILED
        observation = {
            "source_id": source_id,
            "status": status.value,
            "captured_at": response.capture_completed_at,
            "available_at": available_at,
            "reason": failure,
            "claim_ceiling": definition.claim_ceiling,
            "summary": dict(summary),
        }
        observation_path = self._store.seal_observation(
            reference=reference,
            observation=observation,
        )
        return CaptureResult(
            source_id=source_id,
            status=status,
            capture_id=str(reference["capture_id"]),
            captured_at=response.capture_completed_at,
            available_at=available_at,
            raw_ref=reference,
            observation_path=observation_path,
            reason=failure,
            summary=summary,
        )

    def collect_default_sources(
        self,
        *,
        family: str | None = None,
        include_streams: bool = False,
    ) -> tuple[CaptureResult, ...]:
        results = []
        for source in self._catalog.list():
            definition = source.definition
            if not definition.default_enabled:
                continue
            if definition.stream and not include_streams:
                continue
            if family and definition.family != family:
                continue
            results.append(self.collect(definition.source_id))
            if definition.provider == "OKX":
                time.sleep(0.45)
            elif definition.provider == "FRED graph CSV":
                time.sleep(0.25)
        if include_streams:
            for source in self._catalog.list():
                definition = source.definition
                if (
                    definition.access_mode is AccessMode.NO_AUTH
                    and definition.stream
                    and (not family or definition.family == family)
                ):
                    results.append(self.collect(definition.source_id))
        return tuple(results)

    def import_manual(
        self,
        source_id: str,
        *,
        source_file: Path,
        observed_at: str,
        available_at: str,
        source_url: str | None = None,
    ) -> CaptureResult:
        source = self._catalog.get(source_id)
        definition = source.definition
        captured_at = _canonical(self._clock.now())
        if definition.transport is not TransportKind.MANUAL_FILE:
            return _terminal_without_capture(
                definition=definition,
                status=CaptureStatus.CAPTURE_FAILED,
                reason="SOURCE_IS_NOT_MANUAL_FILE",
                captured_at=captured_at,
            )
        reference, raw = self._store.import_manual_file(
            definition=definition,
            source_file=source_file,
            observed_at=observed_at,
            available_at=available_at,
            captured_at=captured_at,
            source_url=source_url,
        )
        content_type = mimetypes.guess_type(source_file.name)[0] or "application/octet-stream"
        response = TransportResponse(
            protocol="MANUAL_FILE",
            status_code=None,
            final_url=source_url or definition.endpoint,
            stored_url=source_url or definition.endpoint,
            headers={"content-type": content_type},
            body=raw,
            request_started_at=captured_at,
            response_received_at=captured_at,
            capture_completed_at=captured_at,
            backend="manual-file",
        )
        try:
            summary = source.normalize(body=raw, response=response)
            status = CaptureStatus.OBSERVED_RAW
            reason = None
        except (TypeError, ValueError) as exc:
            summary = {"format": "unparsed", "normalization_error": str(exc)}
            status = CaptureStatus.CAPTURE_FAILED
            reason = "V332_MANUAL_NORMALIZATION_FAILED"
        observation_path = self._store.seal_observation(
            reference=reference,
            observation={
                "source_id": source_id,
                "status": status.value,
                "captured_at": captured_at,
                "available_at": available_at,
                "observed_at": observed_at,
                "reason": reason,
                "claim_ceiling": definition.claim_ceiling,
                "summary": dict(summary),
            },
        )
        return CaptureResult(
            source_id=source_id,
            status=status,
            capture_id=str(reference["capture_id"]),
            captured_at=captured_at,
            available_at=available_at,
            raw_ref=reference,
            observation_path=observation_path,
            reason=reason,
            summary=summary,
        )


__all__ = ["ExternalDataService", "SystemClock"]
