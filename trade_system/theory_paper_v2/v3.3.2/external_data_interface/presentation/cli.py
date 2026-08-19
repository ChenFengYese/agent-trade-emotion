"""Command-line entry point; it never imports or advances V3.3.1."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from ..application.service import ExternalDataService
from ..domain.contracts import CaptureStatus
from ..infrastructure.catalog import SourceCatalog
from ..infrastructure.http_transport import CompositeTransport
from ..infrastructure.raw_store import FileRawStore


_PARAMETER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def _default_root() -> Path:
    configured = os.environ.get("V332_DATA_ROOT")
    if configured:
        return Path(configured).expanduser()
    return (
        Path.home()
        / ".local"
        / "state"
        / "agent-trade-emotion"
        / "v3.3.2"
        / "external-data"
    )


def _parameters(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError("V332_PARAMETER_KEY_VALUE_REQUIRED")
        key, value = item.split("=", 1)
        if _PARAMETER.fullmatch(key) is None or not value or key in result:
            raise ValueError("V332_PARAMETER_INVALID")
        result[key] = value
    return result


def _service(args: argparse.Namespace) -> ExternalDataService:
    return ExternalDataService(
        catalog=SourceCatalog(),
        transport=CompositeTransport(timeout_seconds=args.timeout),
        store=FileRawStore(args.output_root),
    )


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _status(service: ExternalDataService) -> Mapping[str, Any]:
    catalog = service.catalog()
    counts = Counter(str(item["readiness"]) for item in catalog)
    waiting = [
        {
            "source_id": item["source_id"],
            "access_mode": item["access_mode"],
            "required_env": item["required_env"],
            "required_parameters": item["required_parameters"],
            "reason": item["readiness_reason"],
        }
        for item in catalog
        if item["readiness"] != "READY"
    ]
    return {
        "version": "3.3.2",
        "active_v331_integration": False,
        "source_count": len(catalog),
        "readiness_counts": dict(sorted(counts.items())),
        "waiting_or_bounded_sources": waiting,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v332-external-data",
        description="Isolated read-only external data interface for future V3.3.2",
    )
    parser.add_argument("--output-root", type=Path, default=_default_root())
    parser.add_argument("--timeout", type=float, default=20.0)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("catalog", help="print every source contract and readiness")
    commands.add_parser("status", help="print readiness counts and user-owned setup")
    commands.add_parser("verify-store", help="verify sealed body hashes and observation bindings")

    collect = commands.add_parser("collect", help="capture one finite source window")
    collect.add_argument("source_id")
    collect.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")

    collect_all = commands.add_parser(
        "collect-all", help="capture every default no-account HTTP source once"
    )
    collect_all.add_argument("--family")
    collect_all.add_argument("--include-streams", action="store_true")

    stream = commands.add_parser("stream", help="capture one finite public WSS window")
    stream.add_argument("source_id")
    stream.add_argument("--duration-seconds", type=float, default=12.0)
    stream.add_argument("--max-messages", type=int, default=12)
    stream.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")

    manual = commands.add_parser(
        "import-file", help="seal an official manual CSV/JSON/XML export"
    )
    manual.add_argument("source_id")
    manual.add_argument("--file", type=Path, required=True)
    manual.add_argument("--observed-at", required=True)
    manual.add_argument("--available-at", required=True)
    manual.add_argument("--source-url")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        service = _service(args)
        if args.command == "catalog":
            _emit({"version": "3.3.2", "sources": service.catalog()})
            return 0
        if args.command == "status":
            _emit(_status(service))
            return 0
        if args.command == "verify-store":
            report = FileRawStore(args.output_root).audit()
            _emit(report)
            return 0 if report["invalid_count"] == 0 else 2
        if args.command == "collect":
            result = service.collect(args.source_id, parameters=_parameters(args.param))
            _emit(result.to_dict())
            return 0 if result.status in {CaptureStatus.OBSERVED_RAW, CaptureStatus.OBSERVED_EMPTY} else 2
        if args.command == "stream":
            parameters = _parameters(args.param)
            parameters["duration_seconds"] = str(args.duration_seconds)
            parameters["max_messages"] = str(args.max_messages)
            result = service.collect(args.source_id, parameters=parameters)
            _emit(result.to_dict())
            return 0 if result.status in {CaptureStatus.OBSERVED_RAW, CaptureStatus.OBSERVED_EMPTY} else 2
        if args.command == "collect-all":
            results = service.collect_default_sources(
                family=args.family,
                include_streams=args.include_streams,
            )
            counts = Counter(result.status.value for result in results)
            document = {
                "version": "3.3.2",
                "output_root": str(args.output_root.expanduser().resolve(strict=False)),
                "status_counts": dict(sorted(counts.items())),
                "results": [result.to_dict() for result in results],
            }
            _emit(document)
            return 0 if all(
                result.status in {CaptureStatus.OBSERVED_RAW, CaptureStatus.OBSERVED_EMPTY}
                for result in results
            ) else 2
        if args.command == "import-file":
            result = service.import_manual(
                args.source_id,
                source_file=args.file,
                observed_at=args.observed_at,
                available_at=args.available_at,
                source_url=args.source_url,
            )
            _emit(result.to_dict())
            return 0 if result.status is CaptureStatus.OBSERVED_RAW else 2
    except (KeyError, OSError, TypeError, ValueError) as exc:
        _emit(
            {
                "version": "3.3.2",
                "status": "COMMAND_FAILED",
                "reason": str(exc) or type(exc).__name__,
            }
        )
        return 2
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
