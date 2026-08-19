"""Write-once local repository for V3.4 FORECAST_ONLY strategic states.

The repository contains research artifacts only.  It has no market-data
collector, account, paper-order, testnet, live-order, or credential capability.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from ...domain.contracts.canonical import loads_json_strict
from ...v32_durable_json import write_once_json


_SAFE_ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SLOT_FILE = re.compile(r"[0-9]{8}T(?:00|04|08|12|16|20)0000Z\Z")


class StrategicStateRepositoryError(ValueError):
    """The local forecast-state repository contract was violated."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class FileStrategicStateRepository:
    """Persist one immutable forecast and one immutable outcome per 4H slot."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @staticmethod
    def _asset(value: str) -> str:
        if not isinstance(value, str) or _SAFE_ASSET.fullmatch(value) is None:
            raise StrategicStateRepositoryError("V340_ASSET_ID_INVALID")
        return value

    @staticmethod
    def _slot_key(committee_slot_at: str) -> str:
        if not isinstance(committee_slot_at, str):
            raise StrategicStateRepositoryError("V340_COMMITTEE_SLOT_INVALID")
        key = committee_slot_at.replace("-", "").replace(":", "")
        if _SLOT_FILE.fullmatch(key) is None:
            raise StrategicStateRepositoryError("V340_COMMITTEE_SLOT_INVALID")
        return key

    def _slot_root(self, asset_id: str, committee_slot_at: str) -> Path:
        return self._root / "assets" / self._asset(asset_id) / "slots" / self._slot_key(committee_slot_at)

    def forecast_path(self, asset_id: str, committee_slot_at: str) -> Path:
        return self._slot_root(asset_id, committee_slot_at) / "forecast.json"

    def outcome_path(self, asset_id: str, committee_slot_at: str) -> Path:
        return self._slot_root(asset_id, committee_slot_at) / "outcome.json"

    def evaluation_path(self, asset_id: str, committee_slot_at: str) -> Path:
        return self._slot_root(asset_id, committee_slot_at) / "evaluation.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise StrategicStateRepositoryError(f"V340_ARTIFACT_MISSING:{path.name}") from exc
        try:
            value = loads_json_strict(raw)
        except Exception as exc:
            raise StrategicStateRepositoryError(f"V340_ARTIFACT_INVALID:{path.name}") from exc
        if not isinstance(value, dict):
            raise StrategicStateRepositoryError(f"V340_ARTIFACT_INVALID:{path.name}")
        return value

    def seal_forecast(self, asset_id: str, committee_slot_at: str, record: Mapping[str, Any]) -> str:
        return write_once_json(self.forecast_path(asset_id, committee_slot_at), record)

    def seal_outcome(self, asset_id: str, committee_slot_at: str, record: Mapping[str, Any]) -> str:
        return write_once_json(self.outcome_path(asset_id, committee_slot_at), record)

    def seal_evaluation(self, asset_id: str, committee_slot_at: str, record: Mapping[str, Any]) -> str:
        return write_once_json(self.evaluation_path(asset_id, committee_slot_at), record)

    def load_forecast(self, asset_id: str, committee_slot_at: str) -> dict[str, Any]:
        return self._read(self.forecast_path(asset_id, committee_slot_at))

    def load_outcome(self, asset_id: str, committee_slot_at: str) -> dict[str, Any]:
        return self._read(self.outcome_path(asset_id, committee_slot_at))

    def load_evaluation(self, asset_id: str, committee_slot_at: str) -> dict[str, Any]:
        return self._read(self.evaluation_path(asset_id, committee_slot_at))

    def latest_forecast(self, asset_id: str) -> dict[str, Any] | None:
        root = self._root / "assets" / self._asset(asset_id) / "slots"
        if not root.exists():
            return None
        candidates = []
        for slot in root.iterdir():
            if not slot.is_dir() or _SLOT_FILE.fullmatch(slot.name) is None:
                continue
            forecast = slot / "forecast.json"
            if forecast.is_file():
                candidates.append((slot.name, forecast))
        if not candidates:
            return None
        _, path = max(candidates, key=lambda item: item[0])
        value = self._read(path)
        value["record_sha256"] = _digest(path.read_bytes())
        value["record_path"] = path.relative_to(self._root).as_posix()
        return value


__all__ = ["FileStrategicStateRepository", "StrategicStateRepositoryError"]
