"""Offline-testable, fail-closed SD0 metered document client (no ZIP GET)."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
R3_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r3-repair.v1.json"
R3_DECISION_PHYSICAL_SHA256 = "51c4e532c451472dbf0dbf02e1fae08fd994c1c92797b2f39ff1b1e68b699faf"
R3_DECISION_SHA256 = "1e77ed08350f998ad4bc4c7fa9ced261373fb824b7cd3cb537c3eecb5177aeb7"
R3_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R3_REPAIR.v1"
R3_DECISION_STATE = "CONTINUE_SD0_SUSPENSION_AUTHORIZE_TWO_FILE_R3_REPAIR"
R4_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r4-repair.v1.json"
R4_DECISION_PHYSICAL_SHA256 = "09581d04f9b7e8ca9dd32185d5efe8d2872ec311048cbdf7be546121660b643d"
R4_DECISION_SHA256 = "f427f93794c7db76a3cf9090f2cdd10e080a6c786e6d1de6c7f73fa2d7d0c283"
R4_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R4_REPAIR.v1"
R4_DECISION_STATE = "CONTINUE_R3_PRODUCTION_SUSPENSION_AUTHORIZE_TWO_FILE_R4_REPAIR"
R5_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r5-repair.v1.json"
R5_DECISION_PHYSICAL_SHA256 = "9701d528322cf85795405069b5aa0b10160d4db2923096c5fdd10ac5c60a46a9"
R5_DECISION_SHA256 = "9389912b333bbec965a7efb4e1368e03cc7ea2b83843908553693cf2e609e112"
R5_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R5_REPAIR.v1"
R5_DECISION_STATE = "CONTINUE_R3_R4_PRODUCTION_SUSPENSION_AUTHORIZE_TWO_FILE_R5_REPAIR"
R6_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r6-repair.v1.json"
R6_DECISION_PHYSICAL_SHA256 = "8c736c54273075065fa56757614e95554666ec6dadae831a57652f5bfbdb7b50"
R6_DECISION_SHA256 = "a15e4e51c2f3a1f7a643d72865cecaaa691d8218b3f28d0cec2bfdeffe3fad44"
R6_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R6_REPAIR.v1"
R6_DECISION_STATE = "REJECT_R5_CANDIDATE_CONTINUE_R3_R4_R5_SUSPENSION_AUTHORIZE_TWO_FILE_R6_REPAIR"
R6_COMPLETION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r6-completion.v1.json"
R6_COMPLETION_PHYSICAL_SHA256 = "fee4bbae7410ba29dd58b253885c19682834520085a5a8cdfdcbc58007f0266b"
R6_COMPLETION_SHA256 = "65477842be4b90700f08b7e217f9c798815c4ad4ec6780cb5cdffcbc4556ec0b"
R6_COMPLETION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R6_COMPLETION.v1"
R6_COMPLETION_STATE = "ACCEPT_R6_REPAIR_KEEP_NETWORK_SUSPENDED_PENDING_SEPARATE_RESUME_BINDING"
R7_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r7-gate-rebinding.v1.json"
R7_DECISION_PHYSICAL_SHA256 = "a709e7f05d25d7fff2dd08730e1ca7caa16789de9b23801f419073fdd2565783"
R7_DECISION_SHA256 = "c36327f4e67aee112b07e985ab71a49c40095cfe0a7ee32efd6a944abf10196f"
R7_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R7_GATE_REBINDING.v1"
R7_DECISION_STATE = "AUTHORIZE_TWO_FILE_R7_GATE_REBINDING_KEEP_PRODUCTION_UNCONDITIONALLY_SUSPENDED_PENDING_FUTURE_SOL_FINAL_DECISION"
R7_COMPLETION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r7-gate-rebinding-completion.v1.json"
R7_COMPLETION_PHYSICAL_SHA256 = "ae40e89edef9494f5167cbfa60f4c43457e7aac26513c5618f8c36b8e8ec96e2"
R7_COMPLETION_SHA256 = "a8a091e1129f7b79eeee75bb51ae362d68af72b42c59a0d31b4c6521ec384c10"
R7_COMPLETION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R7_GATE_REBINDING_COMPLETION.v1"
R7_COMPLETION_STATE = "ACCEPT_GATE_REBOUND_CANDIDATE_KEEP_PRODUCTION_SUSPENDED"
R8_DECISION_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-client-p0-r8-activation-route.v1.json"
R8_DECISION_PHYSICAL_SHA256 = "6e99a086e7b03b0762beae26d586c4854b0d58591cc76a291c68dd703f6ed593"
R8_DECISION_SHA256 = "6b6c7605a19e464de16db2507fb9389a2bd8a3da083ce79728f643985b7c813c"
R8_DECISION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R8_ACTIVATION_ROUTE.v1"
R8_DECISION_STATE = "AUTHORIZE_TWO_FILE_R8_CALL_LAYER_ACTIVATION_ROUTE_KEEP_PRODUCTION_SUSPENDED_PENDING_EXTERNAL_SOL_COMPLETION"
R8_COMPLETION_SCHEMA = "sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion-decision.v1"
R8_COMPLETION_ID = "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_CLIENT_P0_R8_ACTIVATION_ROUTE_COMPLETION.v1"
R8_COMPLETION_STATE = "ACCEPT_R8_EXACT_POST_PATCH_CALL_LAYER_ROUTE_AUTHORIZE_CAPABILITY_SCOPED_SD0_PREFLIGHT_AND_SEVEN_REQUESTS"
CLIENT_VERSION = "pitar1-sd0-metered-fetch-v1"
WORKSPACE = "/Users/wt/Documents/agent-trade-emotion"
BRANCH = "codex/s0-research-foundation"
HEAD = "7ca3fc4f99a57f98217e703f222b295653ace87e"
# Authority documents are bound to this immutable issuance context.  The
# mutable runtime constants below are only used by isolated offline fixtures.
AUTH_WORKSPACE, AUTH_BRANCH, AUTH_HEAD = WORKSPACE, BRANCH, HEAD
PROXY = "http://127.0.0.1:7897"
PREFLIGHT_PATH = "artifacts/pit_authority_replay_sd0_preflight.v1.json"
NETWORK_PATHS = (
    ".runtime/pitar1-sd0-v1/receipts/requests.ndjson", ".runtime/pitar1-sd0-v1/receipts/response_headers.ndjson",
    ".runtime/pitar1-sd0-v1/documents/binance-public-data-readme.md", ".runtime/pitar1-sd0-v1/documents/binance-public-data-license.txt",
    ".runtime/pitar1-sd0-v1/documents/btcusdt-1m-2024-03.zip.checksum.txt", ".runtime/pitar1-sd0-v1/receipts/btcusdt-1m-2024-03-zip-head.v1.json",
    "artifacts/pit_authority_replay_sd0_closure_report.v1.json", "config/pit_authority_replay.sd0_artifact_inventory.v1.json",
)
STATIC_PATHS = (
    "archive/authority/PIT_AUTHORITY_REPLAY_SD0_CLOSURE_SPEC_v1_0.md", "config/pit_authority_replay.sd0_measurement_contract.v1.json",
    "config/pit_authority_replay.sd0_request_plan.v1.json", "trade_system/pit_authority_replay_sd0_metered_fetch_v1.py",
    "tests/test_pit_authority_replay_sd0_metered_fetch_v1.py",
)
EXACT = (
    ("SD0-001", "HEAD", "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", 0, ("text/plain", "text/markdown")),
    ("SD0-002", "GET", "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", 1048576, ("text/plain", "text/markdown")),
    ("SD0-003", "HEAD", "https://raw.githubusercontent.com/binance/binance-public-data/master/LICENSE", 0, ("text/plain", "text/markdown")),
    ("SD0-004", "GET", "https://raw.githubusercontent.com/binance/binance-public-data/master/LICENSE", 1048576, ("text/plain", "text/markdown")),
    ("SD0-005", "HEAD", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-03.zip.CHECKSUM", 0, ("text/plain", "application/octet-stream")),
    ("SD0-006", "GET", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-03.zip.CHECKSUM", 65536, ("text/plain", "application/octet-stream")),
    ("SD0-007", "HEAD", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-03.zip", 0, ("application/zip", "application/octet-stream", "binary/octet-stream")),
)
ROUTE_BINDING = {
    "route_id": "RSR-PITAR1-SD0-DUAL-LANE-PHASED-v1", "decision_id": "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_D0_PHASED_ROUTE.v1",
    "decision_path": "config/sol_decision.research-system-pit-authority-replay-sd0-d0-phased-route.v1.json",
    "decision_physical_sha256": "776a7b69c2655dd76eb84ccab12b3fbac30aef6a81b0f6ebad27ab391b129ec0",
    "decision_canonical_sha256": "a777dc9411f638f1d3728f7f98f4ccbb64673f06b8f344dd3489efcdc5b79eeb",
    "cwd": WORKSPACE, "branch": BRANCH, "head": HEAD,
}
ROUTE_DECISION_PHYSICAL_SHA256 = "776a7b69c2655dd76eb84ccab12b3fbac30aef6a81b0f6ebad27ab391b129ec0"
ROUTE_DECISION_CANONICAL_SHA256 = "a777dc9411f638f1d3728f7f98f4ccbb64673f06b8f344dd3489efcdc5b79eeb"
CONTRACT_PHYSICAL_SHA256 = "e2cd42a3930e0ede4d5d003742c2abdc76faa755ae86d20074c9d1f60f79e681"
CONTRACT_CANONICAL_SHA256 = "4ed9f22451ede5c834c20e4f1786d344847166b646f9a1b17d2948e16c617a5b"
PLAN_PHYSICAL_SHA256 = "3f2f487f824643d870bb9d023e6d883e4c7d28bc9fb0bc769cb5d21253a7079c"
PLAN_CANONICAL_SHA256 = "a334816cca1cbdf676e1b935a3404f5803d4ee892c25d2e1d7d34d3a02ea6fe7"
AUTH_ROUTE_DECISION_PHYSICAL_SHA256, AUTH_ROUTE_DECISION_CANONICAL_SHA256 = ROUTE_DECISION_PHYSICAL_SHA256, ROUTE_DECISION_CANONICAL_SHA256
AUTH_CONTRACT_PHYSICAL_SHA256, AUTH_CONTRACT_CANONICAL_SHA256 = CONTRACT_PHYSICAL_SHA256, CONTRACT_CANONICAL_SHA256
AUTH_PLAN_PHYSICAL_SHA256, AUTH_PLAN_CANONICAL_SHA256 = PLAN_PHYSICAL_SHA256, PLAN_CANONICAL_SHA256
STATIC_BUILD_PATHS = {"spec_path": STATIC_PATHS[0], "measurement_contract_path": STATIC_PATHS[1], "request_plan_path": STATIC_PATHS[2], "client_path": STATIC_PATHS[3], "test_path": STATIC_PATHS[4]}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM = re.compile(r"^([0-9a-f]{64})\s+\*?(BTCUSDT-1m-2024-03\.zip)$", re.I)
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_CL = re.compile(r"^(?:0|[1-9][0-9]{0,8})$")
_CAPABILITY_LOCK = threading.RLock()
_CAPABILITIES: dict[int, "_CapabilitySession"] = {}
_READY: dict[str, "_ReadyRecord"] = {}
_INITIAL_ROOT = ROOT.resolve()

class SD0Error(RuntimeError):
    def __init__(self, state: str, message: str):
        super().__init__(message); self.state = state

@dataclass(frozen=True)
class Spec:
    request_id: str; method: str; url: str; cap: int; content_types: tuple[str, ...]
@dataclass(frozen=True)
class HttpResponse:
    status_code: int | None; headers: tuple[tuple[str, str], ...]; body: Any; tls_validation_result: str = "VALIDATED"; transport_error: str | None = None; header_complete: bool = True; error_class: str | None = None; terminal_state: str | None = None
@dataclass(frozen=True)
class ReadyPreflight:
    _snapshot: bytes; digest: str
    @property
    def document(self) -> dict[str, Any]:
        return _strict_json(self._snapshot)
@dataclass(frozen=True)
class NormalizedHeaders:
    pairs: tuple[tuple[str, str], ...]; evidence: bytes; state: str | None
    def values(self, name: str) -> tuple[str, ...]: return tuple(value for key,value in self.pairs if key.lower()==name)

class _ActivationCapability:
    """Opaque identity token.  Registry membership, never its fields, authorizes use."""
    __slots__ = ()
    def __reduce__(self) -> Any: raise TypeError("capability is process-local")
    def __copy__(self) -> Any: raise TypeError("capability is process-local")
    def __deepcopy__(self, memo: Any) -> Any: raise TypeError("capability is process-local")

@dataclass
class _CapabilitySession:
    capability: _ActivationCapability; root: Path; root_device: int; root_inode: int; pid: int
    completion_raw: bytes; completion_physical: str; completion_canonical: str
    activation_id: str; monotonic_expiry: float; client: dict[str, Any]; test: dict[str, Any]
    pair_sha256: str; permissions: dict[str, bool]; state: str = "MINTED"
    ready: ReadyPreflight | None = None; ready_digest: str | None = None; run_id: str | None = None

@dataclass(frozen=True)
class _ReadyRecord:
    snapshot: bytes; context: dict[str, Any]; capability: _ActivationCapability; capability_id: int
    completion_physical: str; completion_canonical: str; activation_id: str; monotonic_deadline: float
    run_id: str; ready: ReadyPreflight; ready_digest: str
    def __getitem__(self, index: int) -> Any: return (self.snapshot, self.context)[index]
    def __iter__(self): return iter((self.snapshot, self.context))

def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _canon(value: Any) -> bytes: return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
def _now() -> str: return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
def _self(domain: str, value: Mapping[str, Any], field: str) -> str:
    plain = dict(value); plain.pop(field, None); return _sha(domain.encode() + b"\0" + _canon(plain))
def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out: raise ValueError("duplicate JSON key")
        out[key] = value
    return out
def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value): raise ValueError("nonfinite")
    if isinstance(value, list): return [_finite(item) for item in value]
    if isinstance(value, dict): return {key: _finite(item) for key, item in value.items()}
    return value
def _strict_json(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if not isinstance(value, dict): raise ValueError("object required")
        return _finite(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", "strict JSON required") from exc

def _read_exact_gate_document(root: Path, relative_path: str, physical_sha256: str, label: str) -> dict[str, Any]:
    """Reject symlink/nonregular/drifted authority before JSON parsing."""
    path = root / relative_path
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise OSError("nonregular authority")
        raw = path.read_bytes()
    except OSError as exc:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", f"{label} gate unavailable") from exc
    if _sha(raw) != physical_sha256:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", f"{label} gate physical identity mismatch")
    try:
        return _strict_json(raw)
    except SD0Error as exc:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", f"{label} gate malformed") from exc

def _exact_pair(value: Any, client_disposition: str, test_disposition: str, pair_key: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = {
        "client": {"path": "trade_system/pit_authority_replay_sd0_metered_fetch_v1.py", "size_bytes": 54422,
                   "physical_sha256": "664ba9fcae87324df281adaa40df8c979664d1ccea61cba258a1a762bf2f665f",
                   "disposition" if pair_key == "accepted_candidate" else "input_disposition": client_disposition},
        "test": {"path": "tests/test_pit_authority_replay_sd0_metered_fetch_v1.py", "size_bytes": 91675,
                 "physical_sha256": "d544c80f6e3bb341777cb1215bef1400f59339674872adb8dfa988577e57c038",
                 "disposition" if pair_key == "accepted_candidate" else "input_disposition": test_disposition},
        ("exact_candidate_pair_sha256" if pair_key == "accepted_candidate" else "exact_input_pair_sha256"): "bbbb62ba717cf96a87242b7ef74fee82b6f608d9b28d8d1a3b8e171060755657",
        "pair_formula": "sha256(client_path_utf8 || 0x00 || client_physical_sha256_ascii || 0x00 || test_path_utf8 || 0x00 || test_physical_sha256_ascii)",
        **({} if pair_key == "accepted_candidate" else {"binding_result": "MATCH", "hard_rule": "Terra must stop without editing if either input file path, size, physical hash, branch, or HEAD differs from this exact authorization."}),
    }
    return all(value.get(key) == item for key, item in expected.items())

def _verify_existing_authority_chain(root: Path) -> None:
    """Authenticate R3--R7 without producing a positive execution grant."""
    decision = _read_exact_gate_document(root, R3_DECISION_PATH, R3_DECISION_PHYSICAL_SHA256, "R3")
    if (
        decision.get("decision_sha256") != R3_DECISION_SHA256
        or _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r3-repair/v1", decision, "decision_sha256") != R3_DECISION_SHA256
        or decision.get("decision_id") != R3_DECISION_ID
        or decision.get("decision_state") != R3_DECISION_STATE
        or decision.get("issue", {}).get("issue_id") != "PITAR1-SD0-CLIENT-P0-R3"
        or decision.get("workspace_identity", {}).get("cwd") != AUTH_WORKSPACE
        or decision.get("workspace_identity", {}).get("branch") != AUTH_BRANCH
        or decision.get("workspace_identity", {}).get("head") != AUTH_HEAD
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R3 gate identity mismatch")
    r4 = _read_exact_gate_document(root, R4_DECISION_PATH, R4_DECISION_PHYSICAL_SHA256, "R4")
    if (
        r4.get("decision_sha256") != R4_DECISION_SHA256
        or _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r4-repair/v1", r4, "decision_sha256") != R4_DECISION_SHA256
        or r4.get("decision_id") != R4_DECISION_ID or r4.get("decision_state") != R4_DECISION_STATE
        or r4.get("issue", {}).get("issue_id") != "PITAR1-SD0-CLIENT-P0-R4"
        or r4.get("workspace_identity", {}).get("cwd") != AUTH_WORKSPACE or r4.get("workspace_identity", {}).get("branch") != AUTH_BRANCH or r4.get("workspace_identity", {}).get("head") != AUTH_HEAD
        or r4.get("authority_bindings", {}).get("r3_blocker_and_repair_decision", {}) != {"path":R3_DECISION_PATH,"decision_id":R3_DECISION_ID,"decision_state":R3_DECISION_STATE,"size_bytes":30654,"physical_sha256":R3_DECISION_PHYSICAL_SHA256,"canonical_sha256":R3_DECISION_SHA256,"binding_result":"MATCH","effect":"The exact R3 production suspension remains authoritative and must not be weakened, replaced, bypassed, or automatically resumed by this R4 repair."}
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R4 gate identity mismatch")
    r5 = _read_exact_gate_document(root, R5_DECISION_PATH, R5_DECISION_PHYSICAL_SHA256, "R5")
    r4_binding=r5.get("authority_bindings", {}).get("r4_blocker_and_repair_decision", {})
    if (
        r5.get("decision_sha256") != R5_DECISION_SHA256
        or _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r5-repair/v1", r5, "decision_sha256") != R5_DECISION_SHA256
        or r5.get("decision_id") != R5_DECISION_ID or r5.get("decision_state") != R5_DECISION_STATE
        or r5.get("issue", {}).get("issue_id") != "PITAR1-SD0-CLIENT-P0-R5"
        or r5.get("workspace_identity", {}).get("cwd") != AUTH_WORKSPACE or r5.get("workspace_identity", {}).get("branch") != AUTH_BRANCH or r5.get("workspace_identity", {}).get("head") != AUTH_HEAD
        or r4_binding.get("path") != R4_DECISION_PATH or r4_binding.get("decision_id") != R4_DECISION_ID or r4_binding.get("decision_state") != R4_DECISION_STATE
        or r4_binding.get("physical_sha256") != R4_DECISION_PHYSICAL_SHA256 or r4_binding.get("canonical_sha256") != R4_DECISION_SHA256 or r4_binding.get("binding_result") != "MATCH"
        or r5.get("authority_bindings", {}).get("r3_blocker_and_repair_decision", {}).get("canonical_sha256") != R3_DECISION_SHA256
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R5 gate identity mismatch")
    r6=_read_exact_gate_document(root,R6_DECISION_PATH,R6_DECISION_PHYSICAL_SHA256,"R6")
    r5_binding=r6.get("authority_bindings",{}).get("r5_blocker_and_repair_decision",{})
    if (r6.get("decision_sha256"),_self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r6-repair/v1",r6,"decision_sha256"),r6.get("decision_id"),r6.get("decision_state"),r6.get("issue",{}).get("issue_id"),r6.get("workspace_identity",{}).get("cwd"),r6.get("workspace_identity",{}).get("branch"),r6.get("workspace_identity",{}).get("head")) != (R6_DECISION_SHA256,R6_DECISION_SHA256,R6_DECISION_ID,R6_DECISION_STATE,"PITAR1-SD0-CLIENT-P0-R6",AUTH_WORKSPACE,AUTH_BRANCH,AUTH_HEAD) or (r5_binding.get("path"),r5_binding.get("decision_id"),r5_binding.get("decision_state"),r5_binding.get("physical_sha256"),r5_binding.get("canonical_sha256"),r5_binding.get("binding_result")) != (R5_DECISION_PATH,R5_DECISION_ID,R5_DECISION_STATE,R5_DECISION_PHYSICAL_SHA256,R5_DECISION_SHA256,"MATCH"):
        raise SD0Error("WAIT_DATA_NO_FALLBACK","R6 gate identity mismatch")
    r6_completion = _read_exact_gate_document(root, R6_COMPLETION_PATH, R6_COMPLETION_PHYSICAL_SHA256, "R6 completion")
    completion_scope = r6_completion.get("completion_scope", {})
    completion_decision = r6_completion.get("completion_decision", {})
    r6_predecessor = r6_completion.get("frozen_authority_bindings", {}).get("r6_repair_decision", {})
    if (
        (r6_completion.get("decision_sha256"), _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r6-completion/v1", r6_completion, "decision_sha256"), r6_completion.get("decision_id"), r6_completion.get("decision_state"))
        != (R6_COMPLETION_SHA256, R6_COMPLETION_SHA256, R6_COMPLETION_ID, R6_COMPLETION_STATE)
        or (r6_completion.get("workspace_identity", {}).get("cwd"), r6_completion.get("workspace_identity", {}).get("branch"), r6_completion.get("workspace_identity", {}).get("head")) != (AUTH_WORKSPACE, AUTH_BRANCH, AUTH_HEAD)
        or not _exact_pair(r6_completion.get("accepted_candidate"), "ACCEPT_OFFLINE_SAFE_BASELINE_PRODUCTION_SUSPENSION_REMAINS", "ACCEPT_R6_INTEGRATED_REGRESSION_BASE", "accepted_candidate")
        or (completion_scope.get("completion_result"), completion_scope.get("precheck_safe"), completion_scope.get("network_resume"), completion_scope.get("workspace_preflight_resume"), completion_scope.get("workspace_runtime_resume"), completion_scope.get("automatic_resume")) != ("ACCEPT", "YES_OFFLINE_ONLY", False, False, False, False)
        or (completion_decision.get("production_preflight"), completion_decision.get("production_seven_request_route"), completion_decision.get("automatic_effect_on_client_gate")) != ("SUSPENDED", "SUSPENDED", "NONE")
        or (r6_predecessor.get("path"), r6_predecessor.get("decision_id"), r6_predecessor.get("decision_state"), r6_predecessor.get("size_bytes"), r6_predecessor.get("physical_sha256"), r6_predecessor.get("canonical_sha256"), r6_predecessor.get("binding_result"))
        != (R6_DECISION_PATH, R6_DECISION_ID, R6_DECISION_STATE, 35592, R6_DECISION_PHYSICAL_SHA256, R6_DECISION_SHA256, "MATCH")
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R6 completion gate identity mismatch")
    r7 = _read_exact_gate_document(root, R7_DECISION_PATH, R7_DECISION_PHYSICAL_SHA256, "R7")
    r7_scope = r7.get("authorization_scope", {})
    r7_binding = r7.get("authority_bindings", {}).get("r6_completion_decision", {})
    r7_permissions = r7.get("permission_matrix", {})
    r7_contract = r7.get("mandatory_gate_rebinding_contract", {})
    if (
        (r7.get("decision_sha256"), _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r7-gate-rebinding/v1", r7, "decision_sha256"), r7.get("decision_id"), r7.get("decision_state"))
        != (R7_DECISION_SHA256, R7_DECISION_SHA256, R7_DECISION_ID, R7_DECISION_STATE)
        or (r7.get("workspace_identity", {}).get("cwd"), r7.get("workspace_identity", {}).get("branch"), r7.get("workspace_identity", {}).get("head")) != (AUTH_WORKSPACE, AUTH_BRANCH, AUTH_HEAD)
        or not _exact_pair(r7.get("authorized_input_pair"), "EXACT_ACCEPTED_R6_OFFLINE_SAFE_BASELINE", "EXACT_ACCEPTED_R6_REGRESSION_BASELINE", "authorized_input_pair")
        or r7.get("minimal_two_file_authorization", {}).get("exact_mutable_file_allowlist") != ["trade_system/pit_authority_replay_sd0_metered_fetch_v1.py", "tests/test_pit_authority_replay_sd0_metered_fetch_v1.py"]
        or (r7.get("minimal_two_file_authorization", {}).get("authorized"), r7.get("minimal_two_file_authorization", {}).get("maximum_mutable_files"), r7.get("minimal_two_file_authorization", {}).get("existing_files_only"), r7.get("minimal_two_file_authorization", {}).get("new_marker_files"), r7.get("minimal_two_file_authorization", {}).get("new_resume_files"), r7.get("minimal_two_file_authorization", {}).get("new_runtime_files")) != (True, 2, True, 0, 0, 0)
        or (r7_scope.get("automatic_resume"), r7_scope.get("production_preflight_permission"), r7_scope.get("production_runtime_permission"), r7_scope.get("network_permission"), r7_scope.get("active_g1_permission"), r7_scope.get("data_or_trading_permission")) != (False, False, False, False, False, False)
        or (r7_contract.get("successful_validation_return_allowed"), r7_contract.get("capability_return_allowed"), r7_contract.get("local_pass_override_allowed"), r7_contract.get("environment_override_allowed"), r7_contract.get("dynamic_decision_discovery_allowed"), r7_contract.get("marker_or_resume_file_lookup_allowed"), r7_contract.get("automatic_resume_after_client_change"), r7_contract.get("automatic_resume_after_tests_pass"), r7_contract.get("automatic_resume_after_completion_review")) != (False, False, False, False, False, False, False, False, False)
        or (r7_permissions.get("create_workspace_preflight"), r7_permissions.get("create_workspace_runtime"), r7_permissions.get("tcp_probe_or_network_request"), r7_permissions.get("production_preflight"), r7_permissions.get("production_seven_request_route"), r7_permissions.get("automatic_resume"), r7_permissions.get("real_action"), r7_permissions.get("real_max_risk")) != (False, False, False, False, False, False, "ABSTAIN", 0)
        or (r7_binding.get("path"), r7_binding.get("decision_id"), r7_binding.get("decision_state"), r7_binding.get("size_bytes"), r7_binding.get("physical_sha256"), r7_binding.get("canonical_sha256"), r7_binding.get("binding_result"))
        != (R6_COMPLETION_PATH, R6_COMPLETION_ID, R6_COMPLETION_STATE, 18769, R6_COMPLETION_PHYSICAL_SHA256, R6_COMPLETION_SHA256, "MATCH")
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R7 gate identity mismatch")
    return None

def _identity(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode): raise OSError("nonregular source")
        raw = path.read_bytes()
    except OSError as exc:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "source identity unavailable") from exc
    return {"path": relative, "size_bytes": len(raw), "physical_sha256": _sha(raw)}

def _pair_sha(client: Mapping[str, Any], test: Mapping[str, Any]) -> str:
    return _sha((client["path"] + "\0" + client["physical_sha256"] + "\0" + test["path"] + "\0" + test["physical_sha256"]).encode())

def _r8_authority(root: Path) -> None:
    r7_completion = _read_exact_gate_document(root, R7_COMPLETION_PATH, R7_COMPLETION_PHYSICAL_SHA256, "R7 completion")
    r7_predecessor = r7_completion.get("authority_bindings", {}).get("r7_gate_rebinding_authorization", {})
    r7_permissions = r7_completion.get("permission_matrix", {})
    if (
        (r7_completion.get("decision_sha256"), _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r7-gate-rebinding-completion/v1", r7_completion, "decision_sha256"), r7_completion.get("decision_id"), r7_completion.get("decision_state"))
        != (R7_COMPLETION_SHA256, R7_COMPLETION_SHA256, R7_COMPLETION_ID, R7_COMPLETION_STATE)
        or (r7_completion.get("workspace_identity", {}).get("cwd"), r7_completion.get("workspace_identity", {}).get("branch"), r7_completion.get("workspace_identity", {}).get("head")) != (AUTH_WORKSPACE, AUTH_BRANCH, AUTH_HEAD)
        or (
            r7_predecessor.get("path"), r7_predecessor.get("decision_id"), r7_predecessor.get("decision_state"),
            r7_predecessor.get("size_bytes"), r7_predecessor.get("physical_sha256"),
            r7_predecessor.get("canonical_sha256"), r7_predecessor.get("binding_result"),
            r7_predecessor.get("automatic_next_permission"),
        ) != (
            R7_DECISION_PATH, R7_DECISION_ID, R7_DECISION_STATE, 24580,
            R7_DECISION_PHYSICAL_SHA256, R7_DECISION_SHA256, "MATCH", "NONE",
        )
        or (
            r7_permissions.get("create_workspace_preflight"),
            r7_permissions.get("create_workspace_runtime"),
            r7_permissions.get("tcp_probe_or_network_request"),
            r7_permissions.get("production_preflight"),
            r7_permissions.get("production_seven_request_route"),
            r7_permissions.get("automatic_next_permission"),
            r7_permissions.get("real_action"),
            r7_permissions.get("real_max_risk"),
        ) != (False, False, False, False, False, "NONE", "ABSTAIN", 0)
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R7 completion identity mismatch")
    r8 = _read_exact_gate_document(root, R8_DECISION_PATH, R8_DECISION_PHYSICAL_SHA256, "R8")
    r7_binding = r8.get("authority_bindings", {}).get("accepted_r7_completion", {})
    r8_pair = r8.get("authorized_input_pair", {})
    if (
        (r8.get("decision_sha256"), _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route/v1", r8, "decision_sha256"), r8.get("decision_id"), r8.get("decision_state"))
        != (R8_DECISION_SHA256, R8_DECISION_SHA256, R8_DECISION_ID, R8_DECISION_STATE)
        or (r8.get("workspace_identity", {}).get("cwd"), r8.get("workspace_identity", {}).get("branch"), r8.get("workspace_identity", {}).get("head")) != (AUTH_WORKSPACE, AUTH_BRANCH, AUTH_HEAD)
        or (r7_binding.get("path"), r7_binding.get("decision_id"), r7_binding.get("decision_state"), r7_binding.get("size_bytes"), r7_binding.get("physical_sha256"), r7_binding.get("canonical_sha256"), r7_binding.get("binding_result"))
        != (R7_COMPLETION_PATH, R7_COMPLETION_ID, R7_COMPLETION_STATE, 16410, R7_COMPLETION_PHYSICAL_SHA256, R7_COMPLETION_SHA256, "MATCH")
        or r8_pair.get("pair_formula") != "sha256(client_path_utf8 || 0x00 || client_physical_sha256_ascii || 0x00 || test_path_utf8 || 0x00 || test_physical_sha256_ascii)"
        or r8.get("selected_activation_route", {}).get("capability_transport") != "EXPLICIT_KEYWORD_ONLY_CALL_ARGUMENT"
        or r8.get("selected_activation_route", {}).get("automatic_resume") is not False
        or r8.get("permission_matrix", {}).get("production_preflight_now") is not False
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "R8 authority identity mismatch")

def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"): raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion time invalid")
    try: return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion time invalid") from exc

_PERMISSIONS = {
    "production_sd0_preflight_via_exact_capability": True, "production_sd0_exact_seven_request_route_via_same_capability": True,
    "automatic_resume": False, "permission_without_capability": False, "permission_from_completion_path_alone": False,
    "permission_from_self_reported_completion_digest_alone": False, "dynamic_completion_discovery": False,
    "environment_or_cli_token": False, "marker_resume_or_capability_file": False, "exact_existing_output_allowlist_only": True,
    "overwrite_or_alternate_output": False, "production_alternate_root": False,
    "production_injected_tcp_probe_opener_or_callback": False, "zip_get": False, "market_row_body": False, "d0": False,
    "adapter_replay_dataset": False, "backtest_paper_testnet_deployment_trading": False, "active_g1": False,
    "credentials_account_orders_funds": False,
}

_R8_TEST_COMMANDS = {
    "syntax": "PYTHONPYCACHEPREFIX=/tmp/pitar1-sd0-r8-pycache python3 -m py_compile trade_system/pit_authority_replay_sd0_metered_fetch_v1.py tests/test_pit_authority_replay_sd0_metered_fetch_v1.py",
    "scoped": "python3 -m unittest -v tests.test_pit_authority_replay_sd0_metered_fetch_v1",
    "combined": "python3 -m unittest -v tests.test_pit_authority_replay_contract_v1 tests.test_pit_authority_replay_sd0_metered_fetch_v1",
}
_R8_TEST_EVIDENCE = {
    "syntax": {"command": _R8_TEST_COMMANDS["syntax"], "result": "PASS", "exit_code": 0},
    "scoped": {"command": _R8_TEST_COMMANDS["scoped"], "tests_run": 68, "passed": 68, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0},
    "combined": {"command": _R8_TEST_COMMANDS["combined"], "tests_run": 137, "passed": 137, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0},
}
_R8_CASES = {f"R8-T{number}": "PASS" for number in range(43, 50)}
_WORKSPACE_OUTPUT_ABSENCE = {path: {"before_absent": True, "after_absent": True} for path in (PREFLIGHT_PATH,) + NETWORK_PATHS}
_EXTERNAL_ACTIONS = {
    "network_requests": 0, "real_tcp_probes": 0, "configured_proxy_access": 0,
    "workspace_preflight_runs": 0, "workspace_runtime_runs": 0, "active_g1_access": 0,
    "market_or_archive_access": 0, "backtest_paper_live_actions": 0,
    "credentials_orders_funds_actions": 0,
}
_MUTATION_AUDIT = {
    "modified_existing_files": [STATIC_PATHS[3], STATIC_PATHS[4]], "new_files": 0,
    "route_changes": 0, "contract_changes": 0, "plan_changes": 0, "schema_changes": 0,
    "spec_changes": 0, "dependency_changes": 0, "authority_changes": 0, "marker_changes": 0,
    "resume_changes": 0, "capability_changes": 0, "completion_changes": 0,
    "runtime_changes": 0, "active_g1_changes": 0,
}
_PRECHECK_SAFE = "YES_OFFLINE_R8_ACCIDENTAL_ACTIVATION_ONLY"
_EXECUTION_CONTRACT = {
    "output_paths": list((PREFLIGHT_PATH,) + NETWORK_PATHS),
    "create_once": True, "no_overwrite": True, "no_alternate_output": True,
    "entrypoints": ["main", "preflight", "persist_ready", "execute"],
    "opaque_capability_required": True, "same_capability_required": True,
    "requests": [
        {"request_id": request_id, "method": method, "url": url, "body_cap_bytes": cap}
        for request_id, method, url, cap, _content_types in EXACT
    ],
    "retry_count": 0, "redirect_count": 0, "concurrency": 1,
    "permission_ceiling": dict(_PERMISSIONS),
}
_COMPLETION_KEYS = {
    "schema_version", "decision_id", "decision_state", "workspace_identity",
    "authority_bindings", "post_patch_pair", "activation", "permission_matrix",
    "frozen_bindings", "implementation_review", "tests", "r8_cases",
    "workspace_output_absence", "external_actions", "mutation_audit",
    "precheck_safe", "execution_contract", "decision_sha256",
}

def _exact_keys(value: Any, keys: Sequence[str] | set[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys)

def _closed_completion_shape(completion: Mapping[str, Any]) -> bool:
    try:
        workspace=completion["workspace_identity"]; authorities=completion["authority_bindings"]; authority=authorities["r8_authorization"]
        pair=completion["post_patch_pair"]; activation=completion["activation"]; frozen=completion["frozen_bindings"]
        reviews=completion["implementation_review"]; review_items=reviews["independent_reviews"]; tests=completion["tests"]
        absence=completion["workspace_output_absence"]; execution=completion["execution_contract"]
        return (
            _exact_keys(completion,_COMPLETION_KEYS)
            and _exact_keys(workspace,("cwd","branch","head"))
            and _exact_keys(authorities,("r8_authorization",))
            and _exact_keys(authority,("path","physical_sha256","canonical_sha256","decision_id","decision_state"))
            and _exact_keys(pair,("client","test","exact_input_pair_sha256","pair_formula"))
            and _exact_keys(pair["client"],("path","size_bytes","physical_sha256"))
            and _exact_keys(pair["test"],("path","size_bytes","physical_sha256"))
            and _exact_keys(activation,("unique_activation_id","not_before_utc","expires_at_utc"))
            and _exact_keys(completion["permission_matrix"],_PERMISSIONS)
            and _exact_keys(frozen,("route","contract","plan"))
            and all(_exact_keys(frozen[key],("physical_sha256","canonical_sha256")) for key in ("route","contract","plan"))
            and _exact_keys(reviews,("independent_reviews",))
            and isinstance(review_items,list) and len(review_items)==2
            and all(_exact_keys(item,("role","reviewer","decision")) for item in review_items)
            and _exact_keys(tests,("syntax","scoped","combined"))
            and _exact_keys(tests["syntax"],("command","result","exit_code"))
            and all(_exact_keys(tests[key],("command","tests_run","passed","failed","errors","skipped","exit_code")) for key in ("scoped","combined"))
            and _exact_keys(completion["r8_cases"],_R8_CASES)
            and _exact_keys(absence,_WORKSPACE_OUTPUT_ABSENCE)
            and all(_exact_keys(absence[path],("before_absent","after_absent")) for path in _WORKSPACE_OUTPUT_ABSENCE)
            and _exact_keys(completion["external_actions"],_EXTERNAL_ACTIONS)
            and _exact_keys(completion["mutation_audit"],_MUTATION_AUDIT)
            and _exact_keys(execution,_EXECUTION_CONTRACT)
            and isinstance(execution["requests"],list) and len(execution["requests"])==7
            and all(_exact_keys(request,("request_id","method","url","body_cap_bytes")) for request in execution["requests"])
            and _exact_keys(execution["permission_ceiling"],_PERMISSIONS)
        )
    except (KeyError,TypeError):
        return False

def _suite_evidence_valid(item: Mapping[str, Any], command: str, minimum: int) -> bool:
    run=item.get("tests_run"); passed=item.get("passed")
    return (
        item.get("command")==command and type(run) is int and run>=minimum
        and type(passed) is int and passed==run
        and all(type(item.get(key)) is int and item[key]==0 for key in ("failed","errors","skipped","exit_code"))
    )

def _validate_completion(raw: bytes, expected_physical: str, expected_canonical: str, root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], float]:
    if not isinstance(raw, bytes) or not all(isinstance(v, str) and _HEX.fullmatch(v) for v in (expected_physical, expected_canonical)):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "explicit completion digests required")
    if _sha(raw) != expected_physical: raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion physical identity mismatch")
    try: completion = _strict_json(raw)
    except SD0Error as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion malformed") from exc
    if (completion.get("decision_sha256"), _self("msta-hed/sol-research-system-pit-authority-replay-sd0-client-p0-r8-activation-route-completion/v1", completion, "decision_sha256")) != (expected_canonical, expected_canonical):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion canonical identity mismatch")
    if not _closed_completion_shape(completion):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion closed schema mismatch")
    activation = completion["activation"]; authority = completion["authority_bindings"]["r8_authorization"]; pair = completion["post_patch_pair"]
    review_items=completion["implementation_review"]["independent_reviews"]; reviewers=[item["reviewer"] for item in review_items]
    tests=completion["tests"]
    client, test = _identity(root, STATIC_PATHS[3]), _identity(root, STATIC_PATHS[4])
    now = datetime.now(timezone.utc); begin, end = _parse_utc(activation.get("not_before_utc")), _parse_utc(activation.get("expires_at_utc"))
    if (
        completion.get("schema_version") != R8_COMPLETION_SCHEMA or completion.get("decision_id") != R8_COMPLETION_ID or completion.get("decision_state") != R8_COMPLETION_STATE
        or completion["workspace_identity"] != {"cwd":AUTH_WORKSPACE,"branch":AUTH_BRANCH,"head":AUTH_HEAD}
        or (authority.get("path"), authority.get("physical_sha256"), authority.get("canonical_sha256"), authority.get("decision_id"), authority.get("decision_state")) != (R8_DECISION_PATH, R8_DECISION_PHYSICAL_SHA256, R8_DECISION_SHA256, R8_DECISION_ID, R8_DECISION_STATE)
        or _canon(pair["client"]) != _canon(client) or _canon(pair["test"]) != _canon(test) or pair.get("exact_input_pair_sha256") != _pair_sha(client, test)
        or pair.get("pair_formula") != "sha256(client_path_utf8 || 0x00 || client_physical_sha256_ascii || 0x00 || test_path_utf8 || 0x00 || test_physical_sha256_ascii)"
        or not isinstance(activation.get("unique_activation_id"), str) or not re.fullmatch(r"PITAR1-SD0-R8-ACT-[0-9a-f]{32}", activation["unique_activation_id"])
        or end <= begin or (end - begin).total_seconds() > 86400 or not (begin <= now < end)
        or _canon(completion["permission_matrix"]) != _canon(_PERMISSIONS)
        or _canon(completion["frozen_bindings"]) != _canon({"route": {"physical_sha256": AUTH_ROUTE_DECISION_PHYSICAL_SHA256, "canonical_sha256": AUTH_ROUTE_DECISION_CANONICAL_SHA256}, "contract": {"physical_sha256": AUTH_CONTRACT_PHYSICAL_SHA256, "canonical_sha256": AUTH_CONTRACT_CANONICAL_SHA256}, "plan": {"physical_sha256": AUTH_PLAN_PHYSICAL_SHA256, "canonical_sha256": AUTH_PLAN_CANONICAL_SHA256}})
        or [item["role"] for item in review_items] != ["SOURCE_MAP_REVIEW","EXECUTED_PROBE_REVIEW"]
        or any(item["decision"]!="ACCEPT" for item in review_items)
        or any(not isinstance(reviewer,str) or not reviewer.strip() for reviewer in reviewers) or len(set(reviewers))!=2
        or _canon(tests["syntax"]) != _canon({"command":_R8_TEST_COMMANDS["syntax"],"result":"PASS","exit_code":0})
        or not _suite_evidence_valid(tests["scoped"],_R8_TEST_COMMANDS["scoped"],68)
        or not _suite_evidence_valid(tests["combined"],_R8_TEST_COMMANDS["combined"],137)
        or _canon(completion["r8_cases"]) != _canon(_R8_CASES)
        or _canon(completion["workspace_output_absence"]) != _canon(_WORKSPACE_OUTPUT_ABSENCE)
        or _canon(completion["external_actions"]) != _canon(_EXTERNAL_ACTIONS)
        or _canon(completion["mutation_audit"]) != _canon(_MUTATION_AUDIT)
        or completion["precheck_safe"] != _PRECHECK_SAFE
        or _canon(completion["execution_contract"]) != _canon(_EXECUTION_CONTRACT)
    ):
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "completion binding mismatch")
    return completion, client, test, time.monotonic() + (end - now).total_seconds()

def _mint_activation_capability(*, completion_raw_bytes: bytes, expected_completion_physical_sha256: str, expected_completion_canonical_sha256: str, exact_resolved_repository_root: Path) -> _ActivationCapability:
    """Private call-layer factory; no path, environment, CLI, or default can mint."""
    if not isinstance(exact_resolved_repository_root, Path): raise SD0Error("WAIT_DATA_NO_FALLBACK", "exact root required")
    try: root = exact_resolved_repository_root.resolve(strict=True)
    except OSError as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "root unavailable") from exc
    if exact_resolved_repository_root != root:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "unresolved root alias forbidden")
    with _CAPABILITY_LOCK:
        _verify_existing_authority_chain(root); _r8_authority(root)
        completion, client, test, deadline = _validate_completion(completion_raw_bytes, expected_completion_physical_sha256, expected_completion_canonical_sha256, root)
        root_stat = root.stat(); fingerprint = (str(root), R8_DECISION_SHA256, expected_completion_physical_sha256, expected_completion_canonical_sha256, _pair_sha(client, test))
        for session in _CAPABILITIES.values():
            if (str(session.root), R8_DECISION_SHA256, session.completion_physical, session.completion_canonical, session.pair_sha256) == fingerprint:
                raise SD0Error("WAIT_DATA_NO_FALLBACK", "capability session already used")
        cap = _ActivationCapability()
        _CAPABILITIES[id(cap)] = _CapabilitySession(cap, root, root_stat.st_dev, root_stat.st_ino, os.getpid(), completion_raw_bytes, expected_completion_physical_sha256, expected_completion_canonical_sha256, completion["activation"]["unique_activation_id"], deadline, client, test, _pair_sha(client, test), dict(_PERMISSIONS))
        return cap

def _is_workspace_root(root_path: Path) -> bool:
    try: return root_path.resolve() == _INITIAL_ROOT
    except OSError: return False

def _is_authority_root(root_path: Path) -> bool:
    try: return root_path.resolve() == ROOT.resolve()
    except OSError: return False

def _revalidate_session_locked(session: _CapabilitySession, root_path: Path, expected_state: str, ready: ReadyPreflight | None = None) -> _ReadyRecord | None:
    """Revalidate every session binding while the lifecycle lock is held."""
    try:
        root = root_path.resolve(strict=True); root_stat = root.stat()
        _verify_existing_authority_chain(root); _r8_authority(root)
        completion, client, test, _deadline = _validate_completion(session.completion_raw, session.completion_physical, session.completion_canonical, root)
        valid = (
            session.state == expected_state and root == session.root
            and (root_stat.st_dev, root_stat.st_ino, os.getpid()) == (session.root_device, session.root_inode, session.pid)
            and time.monotonic() < session.monotonic_expiry and client == session.client and test == session.test
            and completion["activation"]["unique_activation_id"] == session.activation_id
            and session.permissions == _PERMISSIONS
        )
        record = None if ready is None else _READY.get(ready.digest)
        if ready is not None:
            valid = valid and isinstance(record, _ReadyRecord) and (
                record.capability is session.capability and record.capability_id == id(session.capability)
                and record.completion_physical == session.completion_physical
                and record.completion_canonical == session.completion_canonical
                and record.activation_id == session.activation_id
                and record.monotonic_deadline == session.monotonic_expiry
                and record.ready is ready and record.ready_digest == ready.digest
                and record.snapshot == ready._snapshot and record.run_id == ready.document.get("run_id")
                and session.ready is ready and session.ready_digest == ready.digest and session.run_id == record.run_id
            )
        if not valid:
            raise SD0Error("WAIT_DATA_NO_FALLBACK", "capability binding invalid")
        return record
    except BaseException:
        session.state = "CONSUMED_OR_INVALIDATED"
        raise

def _session_for(capability: Any, root_path: Path, expected_state: str, next_state: str) -> _CapabilitySession:
    if capability is None:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "explicit capability required")
    with _CAPABILITY_LOCK:
        if not isinstance(capability, _ActivationCapability) or (session := _CAPABILITIES.get(id(capability))) is None or session.capability is not capability:
            raise SD0Error("WAIT_DATA_NO_FALLBACK", "explicit capability required")
        _revalidate_session_locked(session, root_path, expected_state, session.ready if expected_state in {"PREFLIGHT_READY", "READY_PERSISTED", "EXECUTION_STARTED"} else None)
        session.state = next_state
        return session

def _stage_revalidate(session: _CapabilitySession, root_path: Path, expected_state: str, ready: ReadyPreflight | None = None) -> _ReadyRecord | None:
    with _CAPABILITY_LOCK:
        return _revalidate_session_locked(session, root_path, expected_state, ready)

def _finish_preflight(session: _CapabilitySession, ready: ReadyPreflight | dict[str, Any], context: dict[str, Any] | None = None) -> None:
    with _CAPABILITY_LOCK:
        if not isinstance(ready, ReadyPreflight) or session.state != "PREFLIGHT_STARTED": session.state = "CONSUMED_OR_INVALIDATED"; return
        run_id = ready.document.get("run_id")
        if not isinstance(run_id, str) or context is None:
            session.state = "CONSUMED_OR_INVALIDATED"; return
        if ready.digest in _READY:
            session.state = "CONSUMED_OR_INVALIDATED"
            raise SD0Error("WAIT_DATA_NO_FALLBACK","READY identity already issued")
        record = _ReadyRecord(ready._snapshot, context, session.capability, id(session.capability), session.completion_physical, session.completion_canonical, session.activation_id, session.monotonic_expiry, run_id, ready, ready.digest)
        _READY[ready.digest] = record
        session.ready, session.ready_digest, session.run_id, session.state = ready, ready.digest, run_id, "PREFLIGHT_READY"

def _verify_production_suspension_gate(root_path: Path) -> None:
    """Compatibility wrapper: the positive route is capability-only."""
    _verify_existing_authority_chain(root_path); _r8_authority(root_path)
    raise SD0Error("WAIT_DATA_NO_FALLBACK", "R8 completion capability required")

def _write_all(fd: int, data: bytes) -> None:
    cursor = 0
    while cursor < len(data):
        written = os.write(fd, data[cursor:])
        if written <= 0: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "short write")
        cursor += written

def _normalize_headers(headers: Any) -> NormalizedHeaders:
    """Single total, injective application-header representation for transport and evidence."""
    try:
        pairs=[]
        for pair in headers:
            if not isinstance(pair, tuple) or len(pair)!=2 or not isinstance(pair[0],str) or not isinstance(pair[1],str):
                return NormalizedHeaders((),b"","STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE")
            name,value=pair
            if not _TOKEN.fullmatch(name) or any(ord(ch)<32 or ord(ch) in (127,) for ch in value):
                return NormalizedHeaders(tuple(pairs),_canon([[k,v] for k,v in pairs]),"HALT_PROTOCOL_VIOLATION")
            value.encode("iso-8859-1","strict")
            pairs.append((name,value))
        evidence=_canon([[key,value] for key,value in pairs])
        return NormalizedHeaders(tuple(pairs),evidence,"HALT_RESOURCE_CAP" if len(evidence)>65536 else None)
    except UnicodeError:
        # No lossy replacement is permitted.  Keeping no header evidence and
        # returning a source-contract disposition makes a non-Latin-1
        # Content-Length (including Unicode Nd) a deterministic, non-network
        # failure rather than silently changing the wire value.
        return NormalizedHeaders((),b"","WAIT_DATA_SOURCE_CONTRACT_MISMATCH")
    except MemoryError:
        raise
    except Exception:
        return NormalizedHeaders((),b"","STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE")

def _header_state(spec: Spec, normal: NormalizedHeaders, status: int) -> tuple[str | None, int | None, str, bool]:
    if normal.state: return normal.state,None,"",False
    def vals(name: str) -> tuple[str,...]: return normal.values(name)
    sensitive=("authorization","proxy-authorization","cookie","set-cookie")
    if any(vals(name) for name in sensitive) or vals("location") or vals("transfer-encoding"): return "HALT_PROTOCOL_VIOLATION",None,"",True
    if len(vals("content-length"))>1 or len(vals("content-type"))>1 or len(vals("content-encoding"))>1: return "HALT_PROTOCOL_VIOLATION",None,"",False
    if len(vals("content-length"))==0 or len(vals("content-type"))==0: return "WAIT_DATA_SOURCE_CONTRACT_MISMATCH",None,"",False
    if vals("content-encoding") and vals("content-encoding")[0].strip().lower()!="identity": return "HALT_PROTOCOL_VIOLATION",None,"",False
    raw=vals("content-length")[0]
    if not _CL.fullmatch(raw): return "WAIT_DATA_SOURCE_CONTRACT_MISMATCH",None,"",False
    declared=int(raw)
    content=vals("content-type")[0].split(";",1)[0].strip().lower()
    cap=spec.cap if spec.method=="GET" else (536870912 if spec.request_id=="SD0-007" else {"SD0-001":1048576,"SD0-003":1048576,"SD0-005":65536}[spec.request_id])
    if declared>cap: return "HALT_RESOURCE_CAP",declared,content,False
    if status!=200: return "HALT_PROTOCOL_VIOLATION",declared,content,False
    if content not in spec.content_types or (spec.request_id=="SD0-007" and declared==0): return "WAIT_DATA_SOURCE_CONTRACT_MISMATCH",declared,content,False
    return None,declared,content,False

class SafeRoot:
    """No-follow dirfd boundary; all public failures have a declared state."""
    def __init__(self, root: Path):
        try: self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "unsafe root") from exc
    def close(self) -> None: os.close(self.fd)
    def _parent(self, rel: str, create: bool) -> tuple[int, str]:
        parts = Path(rel).parts
        if not parts or any(part in ("", ".", "..") for part in parts): raise SD0Error("HALT_PROTOCOL_VIOLATION", "unsafe relative path")
        current = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                try: next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                except FileNotFoundError:
                    if not create: os.close(current); return -1, parts[-1]
                    os.mkdir(part, 0o700, dir_fd=current); next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "unsafe parent") from exc
                os.close(current); current = next_fd
            return current, parts[-1]
        except Exception:
            if current >= 0: os.close(current)
            raise
    def exists_or_link(self, rel: str) -> bool:
        parent, name = self._parent(rel, False)
        if parent < 0: return False
        try:
            try: os.stat(name, dir_fd=parent, follow_symlinks=False); return True
            except FileNotFoundError: return False
            except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "output stat") from exc
        finally: os.close(parent)
    def read(self, rel: str) -> bytes:
        parent, name = self._parent(rel, False)
        if parent < 0: raise SD0Error("WAIT_DATA_NO_FALLBACK", "missing required file")
        try:
            try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "missing required file") from exc
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode): raise SD0Error("HALT_PROTOCOL_VIOLATION", "nonregular file")
                chunks=[]
                while True:
                    block=os.read(fd,65536)
                    if not block: return b"".join(chunks)
                    chunks.append(block)
            finally: os.close(fd)
        except SD0Error: raise
        except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "safe read") from exc
        finally: os.close(parent)
    def create(self, rel: str, payload: bytes, *, append: bool=False) -> int:
        parent, name = self._parent(rel, True)
        try:
            flags=os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|(os.O_APPEND if append else 0)
            try: fd=os.open(name,flags,0o600,dir_fd=parent)
            except FileExistsError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "existing output") from exc
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode): raise SD0Error("HALT_PROTOCOL_VIOLATION", "nonregular output")
                _write_all(fd,payload); os.fsync(fd); return fd
            except Exception: os.close(fd); raise
        except SD0Error: raise
        except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "safe create") from exc
        finally: os.close(parent)
    def append(self, fd: int, payload: bytes) -> None:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise SD0Error("HALT_PROTOCOL_VIOLATION", "nonregular ledger")
            _write_all(fd,payload); os.fsync(fd)
        except SD0Error: raise
        except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "safe append") from exc
    def readfd(self, fd: int) -> bytes:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise SD0Error("HALT_PROTOCOL_VIOLATION", "nonregular ledger")
            os.lseek(fd,0,os.SEEK_SET); chunks=[]
            while True:
                block=os.read(fd,65536)
                if not block: return b"".join(chunks)
                chunks.append(block)
        except OSError as exc: raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "ledger read") from exc

class Budget:
    def __init__(self, cap: int, initial: int):
        if initial >= cap: raise SD0Error("HALT_RESOURCE_CAP", "persisted preflight exhausts local artifact cap")
        self.cap=cap; self.used=initial
    def reserve(self, count: int) -> None:
        if count < 0 or self.used + count > self.cap: raise SD0Error("HALT_RESOURCE_CAP", "local artifact cap")
        self.used += count
    def create(self, safe: SafeRoot, rel: str, data: bytes, *, append: bool=False) -> int:
        self.reserve(len(data)); return safe.create(rel,data,append=append)
    def append(self, safe: SafeRoot, fd: int, data: bytes) -> None:
        self.reserve(len(data)); safe.append(fd,data)

def _git(root: Path,*args:str)->str:
    try: return subprocess.check_output(["git",*args],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError): return ""
def _validate_plan(plan: Mapping[str,Any]) -> tuple[Spec,...]:
    exact_keys={"schema_version","plan_id","namespace","route_binding","exact_static_build_paths","proxy_endpoint","protocol","hostname_allowlist","redirect_count","retry_count","concurrency","request_order","resource_caps","protocol_prohibitions","requests","head_and_get_invariants","canonicalization","plan_sha256"}
    if set(plan)!=exact_keys or plan.get("schema_version")!="pitar1-sd0-request-plan.v1" or plan.get("plan_sha256")!=_self("pitar1/sd0-request-plan/v1",plan,"plan_sha256"): raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW","plan schema/digest")
    route=plan["route_binding"]; caps=plan["resource_caps"]; denied=plan["protocol_prohibitions"]
    frozen_caps={"maximum_logical_requests":7,"maximum_total_response_body_bytes":2162688,"maximum_response_header_bytes_per_request":65536,"maximum_total_local_artifact_bytes":10485760,"minimum_free_disk_bytes":16106127360,"maximum_external_cost_usd":0,"per_request_timeout_seconds":15,"total_wall_clock_cap_seconds":120}
    if not isinstance(route,dict) or route != ROUTE_BINDING or plan.get("exact_static_build_paths") != STATIC_BUILD_PATHS or plan.get("proxy_endpoint")!=PROXY or plan.get("protocol")!="HTTPS_ONLY" or plan.get("hostname_allowlist")!=["raw.githubusercontent.com","data.binance.vision"] or (plan.get("redirect_count"),plan.get("retry_count"),plan.get("concurrency"))!=(0,0,1) or plan.get("request_order")!="SD0-001_THROUGH_SD0-007_SEQUENTIAL_STOP_ON_FIRST_FAILURE" or caps != frozen_caps or any(denied.get(key) is not False for key in ("direct_bypass","environment_proxy_override","zip_get","market_row_body_access","source_listing_or_search","credentials_or_cookies","browser_or_web_tool","curl_or_general_purpose_fetcher","fallback_url_or_host")): raise SD0Error("HALT_PROTOCOL_VIOLATION","frozen transport drift")
    if not isinstance(plan["requests"],list) or len(plan["requests"])!=7: raise SD0Error("HALT_PROTOCOL_VIOLATION","request count")
    result=[]
    output_by_request = {"SD0-002": NETWORK_PATHS[2], "SD0-004": NETWORK_PATHS[3], "SD0-006": NETWORK_PATHS[4], "SD0-007": NETWORK_PATHS[5]}
    for index, (raw, item) in enumerate(zip(plan["requests"],EXACT)):
        extras={"paired_get_request_id"} if item[1]=="HEAD" and item[0]!="SD0-007" else ({"required_prior_head_request_id","output_path"} if item[1]=="GET" else {"output_path"})
        expected_extra = ({"paired_get_request_id": EXACT[index + 1][0]} if item[1]=="HEAD" and item[0]!="SD0-007" else ({"required_prior_head_request_id": EXACT[index - 1][0], "output_path": output_by_request[item[0]]} if item[1]=="GET" else {"output_path": output_by_request[item[0]]}))
        if set(raw)!={"request_id","method","url","body_cap_bytes","content_types"}|extras or (raw["request_id"],raw["method"],raw["url"],raw["body_cap_bytes"],tuple(raw["content_types"]))!=item or any(raw[key] != value for key,value in expected_extra.items()): raise SD0Error("HALT_PROTOCOL_VIOLATION","request drift")
        result.append(Spec(*item))
    return tuple(result)
def _load(safe:SafeRoot)->tuple[dict[str,Any],dict[str,Any],tuple[Spec,...]]:
    contract=_strict_json(safe.read(STATIC_PATHS[1])); plan=_strict_json(safe.read(STATIC_PATHS[2]))
    if contract.get("contract_sha256")!=_self("pitar1/sd0-measurement-contract/v1",contract,"contract_sha256"): raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW","contract digest")
    return contract,plan,_validate_plan(plan)
def _schema(contract:Mapping[str,Any],role:str,value:Mapping[str,Any])->None:
    fields=contract["artifact_schemas"][role].get("exact_fields")
    if fields is not None and set(value)!=set(fields): raise SD0Error("HALT_PROTOCOL_VIOLATION","closed schema "+role)

def _route_authority(safe: SafeRoot, plan: Mapping[str, Any]) -> tuple[str, str]:
    binding=plan.get("route_binding")
    if binding != ROUTE_BINDING: raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", "route binding")
    try: data=safe.read(ROUTE_BINDING["decision_path"])
    except SD0Error as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK", "route authority unavailable") from exc
    physical=_sha(data)
    if physical != ROUTE_DECISION_PHYSICAL_SHA256: raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", "route physical")
    route=_strict_json(data)
    canonical=_self("msta-hed/sol-research-system-pit-authority-replay-sd0-d0-phased-route/v1",route,"decision_sha256")
    identity=route.get("route_identity",{})
    if (route.get("decision_sha256"),canonical,route.get("decision_id"),route.get("decision_state"),identity.get("route_id"),identity.get("workspace"),identity.get("branch"),identity.get("head_at_issue")) != (ROUTE_DECISION_CANONICAL_SHA256,ROUTE_DECISION_CANONICAL_SHA256,ROUTE_BINDING["decision_id"],"AUTHORIZED_METERED_SD0_CLOSURE_ROUTE_NETWORK_WAIT_D0_AND_LATER_GATES_LOCKED",ROUTE_BINDING["route_id"],ROUTE_BINDING["cwd"],ROUTE_BINDING["branch"],ROUTE_BINDING["head"]):
        raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW", "route canonical identity")
    return physical,canonical

def _issuing_context(safe: SafeRoot, root_path: Path, contract: Mapping[str, Any], plan: Mapping[str, Any], *, require_preflight_absent: bool) -> dict[str, Any]:
    try:
        resolved = str(root_path.resolve()); opened_root = os.fstat(safe.fd); resolved_root = os.stat(resolved)
        if (opened_root.st_dev, opened_root.st_ino) != (resolved_root.st_dev, resolved_root.st_ino):
            raise SD0Error("WAIT_DATA_NO_FALLBACK", "resolved root differs from opened dirfd")
    except OSError as exc:
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "root identity unavailable") from exc
    route_physical,route_canonical=_route_authority(safe,plan)
    contract_bytes=safe.read(STATIC_PATHS[1]); plan_bytes=safe.read(STATIC_PATHS[2])
    if (_sha(contract_bytes),contract.get("contract_sha256"),_sha(plan_bytes),plan.get("plan_sha256")) != (CONTRACT_PHYSICAL_SHA256,CONTRACT_CANONICAL_SHA256,PLAN_PHYSICAL_SHA256,PLAN_CANONICAL_SHA256): raise SD0Error("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW","contract/plan identity")
    resolved_workspace=str(Path(WORKSPACE).resolve())
    if resolved != resolved_workspace or (plan.get("route_binding"), _git(root_path,"branch","--show-current"), _git(root_path,"rev-parse","HEAD")) != (ROUTE_BINDING,BRANCH,HEAD): raise SD0Error("WAIT_DATA_NO_FALLBACK","external root/git drift")
    authorities=[]
    for binding in contract["authority_bindings"]:
        try: actual=_sha(safe.read(binding["path"]))
        except SD0Error: actual="MISSING"
        authorities.append({"path":binding["path"],"expected_sha256":binding["physical_sha256"],"actual_sha256":actual,"matched":actual==binding["physical_sha256"]})
    statics=[]
    for path in STATIC_PATHS:
        try: digest=_sha(safe.read(path)); present=True
        except SD0Error: digest=None; present=False
        statics.append({"path":path,"present":present,"physical_sha256":digest})
    networks=[{"path":path,"absent":not safe.exists_or_link(path)} for path in NETWORK_PATHS]
    preflight_absent=not safe.exists_or_link(PREFLIGHT_PATH)
    context={"resolved_root":resolved,"root_device":opened_root.st_dev,"root_inode":opened_root.st_ino,"branch":BRANCH,"head":HEAD,"route_binding":dict(ROUTE_BINDING),"route_physical_sha256":route_physical,"route_canonical_sha256":route_canonical,"contract_physical_sha256":_sha(contract_bytes),"contract_canonical_sha256":contract.get("contract_sha256"),"plan_physical_sha256":_sha(plan_bytes),"plan_canonical_sha256":plan.get("plan_sha256"),"authority_binding_results":authorities,"static_path_results":statics,"network_output_absence":networks,"preflight_absent_at_issue":preflight_absent if require_preflight_absent else True,"context_sha256":""}
    context["context_sha256"]=_self("pitar1/sd0-ready-context/v1",context,"context_sha256")
    return context

def _context_is_ready(context: Mapping[str, Any], expected: Mapping[str, Any] | None = None) -> bool:
    try:
        if expected is None or _canon(context) != _canon(expected): return False
        authority=context["authority_binding_results"]; statics=context["static_path_results"]; networks=context["network_output_absence"]
        return (
            context["resolved_root"] == str(Path(WORKSPACE).resolve())
            and isinstance(context["root_device"], int) and isinstance(context["root_inode"], int)
            and (context["root_device"],context["root_inode"]) == (os.stat(context["resolved_root"]).st_dev,os.stat(context["resolved_root"]).st_ino)
            and context["branch"] == BRANCH and context["head"] == HEAD and context["route_binding"] == ROUTE_BINDING
            and (context["route_physical_sha256"],context["route_canonical_sha256"],context["contract_physical_sha256"],context["contract_canonical_sha256"],context["plan_physical_sha256"],context["plan_canonical_sha256"]) == (ROUTE_DECISION_PHYSICAL_SHA256,ROUTE_DECISION_CANONICAL_SHA256,CONTRACT_PHYSICAL_SHA256,CONTRACT_CANONICAL_SHA256,PLAN_PHYSICAL_SHA256,PLAN_CANONICAL_SHA256)
            and [item["path"] for item in statics] == list(STATIC_PATHS)
            and all(item["present"] and _HEX.fullmatch(item["physical_sha256"] or "") for item in statics)
            and all(item["matched"] and _HEX.fullmatch(item["expected_sha256"]) and _HEX.fullmatch(item["actual_sha256"]) for item in authority)
            and [item["path"] for item in networks] == list(NETWORK_PATHS)
            and all(item["absent"] for item in networks)
            and context["preflight_absent_at_issue"] is True
            and context["context_sha256"] == _self("pitar1/sd0-ready-context/v1", context, "context_sha256")
        )
    except (KeyError, TypeError, ValueError):
        return False

def _projection(context: Mapping[str, Any]) -> dict[str, Any]:
    return {"route_binding":context["route_binding"],"authority_binding_results":context["authority_binding_results"],"static_path_results":context["static_path_results"],"output_path_results":context["network_output_absence"]+[{"path":PREFLIGHT_PATH,"absent":True}],"request_plan_sha256":context["plan_canonical_sha256"]}

def _projection_matches(document: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    try: return all(document[key] == value for key,value in _projection(context).items())
    except (KeyError,TypeError): return False

def preflight(root_path:Path=ROOT,*,tests_evidence:Mapping[str,Any]|None=None,tcp_probe:Callable[[str,int],bool]|None=None,capability:Any=None)->ReadyPreflight|dict[str,Any]:
    session = _session_for(capability, root_path, "MINTED", "PREFLIGHT_STARTED")
    if session is not None and _is_workspace_root(root_path) and tcp_probe is not None:
        with _CAPABILITY_LOCK: session.state = "CONSUMED_OR_INVALIDATED"
        raise SD0Error("WAIT_DATA_NO_FALLBACK", "production TCP injection forbidden")
    safe=SafeRoot(root_path)
    try:
        contract,plan,_=_load(safe); failures=[]; authority=[]; static=[]; outputs=[]
        if str(root_path)!=WORKSPACE or _git(root_path,"branch","--show-current")!=BRANCH or _git(root_path,"rev-parse","HEAD")!=HEAD: failures.append("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW")
        for binding in contract["authority_bindings"]:
            try: actual=_sha(safe.read(binding["path"]))
            except SD0Error: actual="MISSING"
            authority.append({"path":binding["path"],"expected_sha256":binding["physical_sha256"],"actual_sha256":actual,"matched":actual==binding["physical_sha256"]})
            if actual!=binding["physical_sha256"]: failures.append("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW")
        for path in STATIC_PATHS:
            try: digest=_sha(safe.read(path)); present=True
            except SD0Error: digest=None; present=False; failures.append("HALT_ROUTE_DRIFT_NEW_SOL_REVIEW")
            static.append({"path":path,"present":present,"physical_sha256":digest})
        for path in NETWORK_PATHS+(PREFLIGHT_PATH,):
            exists=safe.exists_or_link(path); outputs.append({"path":path,"absent":not exists})
            if exists: failures.append("FAIL_CLOSED_NO_OVERWRITE")
        disk=shutil.disk_usage(root_path).free
        if disk<plan["resource_caps"]["minimum_free_disk_bytes"]: failures.append("WAIT_DATA_NO_FALLBACK")
        evidence=dict(tests_evidence or {})
        if set(evidence)!={"command","result","sha256"} or evidence.get("result")!="PASS" or not isinstance(evidence.get("sha256"),str) or not _HEX.fullmatch(evidence["sha256"]): failures.append("WAIT_DATA_NO_FALLBACK")
        accepted=None
        if not failures:
            first=_issuing_context(safe,root_path,contract,plan,require_preflight_absent=True); second=_issuing_context(safe,root_path,contract,plan,require_preflight_absent=True)
            if first != second or not _context_is_ready(first,second): failures.append("WAIT_DATA_NO_FALLBACK")
            else:
                accepted=first; authority=first["authority_binding_results"]; static=first["static_path_results"]; outputs=_projection(first)["output_path_results"]
        if not failures:
            _stage_revalidate(session, root_path, "PREFLIGHT_STARTED")
            tcp=(tcp_probe or _tcp)("127.0.0.1",7897)
            _stage_revalidate(session, root_path, "PREFLIGHT_STARTED")
        else:
            tcp=False
        if not tcp: failures.append("WAIT_DATA_NETWORK_TRANSPORT_NO_REQUESTS")
        state="READY" if not failures else failures[0]
        projected=_projection(accepted) if accepted is not None else {"route_binding":plan["route_binding"],"authority_binding_results":authority,"static_path_results":static,"output_path_results":outputs,"request_plan_sha256":plan["plan_sha256"]}
        doc={"schema_version":"pitar1-sd0-preflight.v1","run_id":"sd0-"+uuid.uuid4().hex,**projected,"disk_free_bytes":disk,"proxy_endpoint":PROXY,"proxy_tcp_preflight":tcp,"client_test_evidence":evidence,"external_requests_sent":0,"terminal_disposition":state,"failure_state":None if state=="READY" else state,"created_at_utc":_now(),"preflight_sha256":""}
        doc["preflight_sha256"]=_self("pitar1/sd0-preflight/v1",doc,"preflight_sha256"); _schema(contract,"NETWORK_AND_RESOURCE_PREFLIGHT_RESULT",doc)
        if state!="READY":
            _finish_preflight(session, doc); return doc
        context=_issuing_context(safe,root_path,contract,plan,require_preflight_absent=True)
        if context != accepted or not _context_is_ready(context,accepted) or not _projection_matches(doc,context):
            doc["terminal_disposition"]="HALT_ROUTE_DRIFT_NEW_SOL_REVIEW"; doc["failure_state"]="HALT_ROUTE_DRIFT_NEW_SOL_REVIEW"; doc["preflight_sha256"]=_self("pitar1/sd0-preflight/v1",doc,"preflight_sha256")
            _finish_preflight(session, doc); return doc
        snapshot=_canon(doc); token=ReadyPreflight(snapshot,doc["preflight_sha256"]); _finish_preflight(session, token, context); return token
    except BaseException:
        if session is not None:
            with _CAPABILITY_LOCK: session.state = "CONSUMED_OR_INVALIDATED"
        raise
    finally: safe.close()
def _ready_snapshot(ready:ReadyPreflight, session:_CapabilitySession)->tuple[bytes,dict[str,Any]]:
    with _CAPABILITY_LOCK:
        record = _revalidate_session_locked(session, session.root, session.state, ready)
        if not isinstance(record, _ReadyRecord) or not isinstance(ready._snapshot,bytes): raise SD0Error("WAIT_DATA_NO_FALLBACK","unissued READY")
        doc=_strict_json(ready._snapshot)
        if _self("pitar1/sd0-preflight/v1",doc,"preflight_sha256")!=ready.digest or doc.get("preflight_sha256")!=ready.digest or doc.get("terminal_disposition")!="READY" or doc.get("external_requests_sent")!=0 or not _projection_matches(doc,record.context):
            session.state = "CONSUMED_OR_INVALIDATED"; raise SD0Error("WAIT_DATA_NO_FALLBACK","READY self validation")
        return ready._snapshot,record.context
def persist_ready(root_path:Path,ready:ReadyPreflight,*,capability:Any=None)->None:
    session = _session_for(capability, root_path, "PREFLIGHT_READY", "READY_PERSISTED")
    snapshot,expected=_ready_snapshot(ready,session); safe=SafeRoot(root_path)
    try:
        contract,plan,_=_load(safe)
        if safe.exists_or_link(PREFLIGHT_PATH): raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "preflight already exists")
        if _issuing_context(safe,root_path,contract,plan,require_preflight_absent=True)!=expected: raise SD0Error("WAIT_DATA_NO_FALLBACK","issuing context drift")
        _stage_revalidate(session, root_path, "READY_PERSISTED", ready)
        fd=safe.create(PREFLIGHT_PATH,snapshot+b"\n"); os.close(fd)
    except BaseException:
        if session is not None:
            with _CAPABILITY_LOCK: session.state = "CONSUMED_OR_INVALIDATED"
        raise
    finally: safe.close()
def _tcp(host:str,port:int)->bool:
    try:
        with socket.create_connection((host,port),timeout=15): return True
    except OSError: return False

class StdlibProxyOpener:
    def __call__(self,spec:Spec)->HttpResponse:
        target=urlsplit(spec.url); proxy=urlsplit(PROXY)
        if target.scheme!="https" or target.hostname not in {"raw.githubusercontent.com","data.binance.vision"}: raise SD0Error("HALT_PROTOCOL_VIOLATION","target")
        conn=http.client.HTTPConnection(proxy.hostname,proxy.port,timeout=15)
        response=None; status=None; headers: list[tuple[str,str]]=[]; complete=False; body: Any=b""; tls="UNAVAILABLE"; terminal=None; error=None
        try:
            conn.set_tunnel(target.hostname,443); conn.connect(); conn.sock=ssl.create_default_context().wrap_socket(conn.sock,server_hostname=target.hostname); tls="VALIDATED"
            conn.putrequest(spec.method,target.path,skip_host=True); conn.putheader("Host",target.hostname); conn.putheader("Accept-Encoding","identity"); conn.putheader("User-Agent",CLIENT_VERSION); conn.endheaders(); response=conn.getresponse(); status=response.status
            iterator=iter(response.getheaders())
            while True:
                try: pair=next(iterator)
                except StopIteration: complete=True; break
                normal_prefix=_normalize_headers(tuple(headers+[pair]))
                headers=list(normal_prefix.pairs)
                if normal_prefix.state is not None: terminal=normal_prefix.state; break
            normal=_normalize_headers(tuple(headers)); state,declared,_content,_secret=_header_state(spec,normal,status)
            if terminal is None: terminal=state
            if spec.method!="HEAD" and terminal is None and declared is not None:
                try: body=response.read(declared)
                except http.client.IncompleteRead as exc: body=exc.partial; terminal="WAIT_DATA_NO_FALLBACK"; error=exc.__class__.__name__
                except (socket.timeout, TimeoutError, ssl.SSLError, ConnectionError, OSError, http.client.HTTPException) as exc: terminal="WAIT_DATA_NO_FALLBACK"; error=exc.__class__.__name__
        except (socket.timeout, TimeoutError, ssl.SSLError, ConnectionError, OSError, http.client.HTTPException) as exc:
            if status is None: raise SD0Error("WAIT_DATA_NO_FALLBACK","pre-response transport failure") from exc
            terminal=terminal or "WAIT_DATA_NO_FALLBACK"; error=exc.__class__.__name__
        except MemoryError:
            raise
        except Exception as exc:
            if status is None: raise
            terminal=terminal or "STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE"; error=exc.__class__.__name__
        finally:
            cleanup_base: BaseException | None = None
            for closer in ((response.close if response is not None and hasattr(response,"close") else None),conn.close):
                if closer is None: continue
                try: closer()
                except BaseException as exc:
                    if isinstance(exc, (MemoryError, KeyboardInterrupt, SystemExit, GeneratorExit)) or not isinstance(exc, Exception):
                        if cleanup_base is None: cleanup_base=exc
                        continue
                    if status is not None and terminal is None: terminal="STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE"; error=exc.__class__.__name__
            if cleanup_base is not None: raise cleanup_base
        if status is None: raise SD0Error("WAIT_DATA_NO_FALLBACK","pre-response transport failure")
        return HttpResponse(status,tuple(headers),body,tls,header_complete=complete,error_class=error,terminal_state=terminal)

def _make_observation(spec:Spec,response:HttpResponse,total:int,started:str,started_ns:int)->tuple[dict[str,Any],dict[str,Any]|None,str|None]:
    normal=_normalize_headers(response.headers); base_state,declared,content,secret=_header_state(spec,normal,response.status_code)
    received=_now(); actual=0; captured=b""
    record={"run_id":"","request_id":spec.request_id,"method":spec.method,"exact_url":spec.url,"hostname":urlsplit(spec.url).hostname,"proxy_endpoint":PROXY,"started_at_utc":started,"finished_at_utc":received,"elapsed_monotonic_ns":time.monotonic_ns()-started_ns,"status_code":response.status_code,"redirect_count":0,"declared_content_length":declared,"response_body_bytes":0,"response_body_sha256":_sha(b""),"response_headers_sha256":_sha(normal.evidence),"tls_validation_result":response.tls_validation_result,"client_version":CLIENT_VERSION,"error_class":response.error_class,"terminal_disposition":"PASS"}
    location=normal.values("location")
    header=None if not response.header_complete or secret or normal.state or len(normal.evidence)>65536 else {"run_id":"","request_id":spec.request_id,"exact_url":spec.url,"status_code":response.status_code,"headers":[[key,value] for key,value in normal.pairs],"header_bytes":len(normal.evidence),"headers_sha256":_sha(normal.evidence),"content_type":content,"declared_content_length":declared,"redirect_location":location[0] if location else None,"received_at_utc":received,"terminal_disposition":"PASS"}
    state=response.terminal_state or ("STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE" if not response.header_complete else None) or base_state
    if not isinstance(response.body,bytes): state=state or "STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE"; record["error_class"]=record["error_class"] or "TypeError"
    else:
        captured=response.body; actual=len(captured); record["response_body_bytes"]=actual; record["response_body_sha256"]=_sha(captured)
    if spec.method=="HEAD" and actual: state="HALT_NO_ROW_LEAK_VIOLATION"
    if state is None and response.transport_error is not None: state="WAIT_DATA_NO_FALLBACK"
    if state is None and (actual>spec.cap or total+actual>2162688 or (spec.method=="GET" and actual!=declared)): state="HALT_RESOURCE_CAP" if actual>spec.cap or total+actual>2162688 else "WAIT_DATA_SOURCE_CONTRACT_MISMATCH"
    return record,header,state
def _observe(spec:Spec,response:HttpResponse,total:int,started:str,started_ns:int)->tuple[dict[str,Any],dict[str,Any]]:
    record,header,state=_make_observation(spec,response,total,started,started_ns)
    if state: raise SD0Error(state,"observed response rejected")
    if header is None: raise SD0Error("HALT_PROTOCOL_VIOLATION","unsafe header")
    return record,header
def _checksum(body:bytes)->str:
    try: lines=[line for line in body.decode("utf-8","strict").splitlines() if line.strip()]
    except UnicodeDecodeError as exc: raise SD0Error("WAIT_DATA_SOURCE_CONTRACT_MISMATCH","checksum encoding") from exc
    match=_CHECKSUM.fullmatch(lines[0].strip()) if len(lines)==1 else None
    if not match: raise SD0Error("WAIT_DATA_SOURCE_CONTRACT_MISMATCH","checksum")
    return match.group(1).lower()

def _identities(safe:SafeRoot,paths:Sequence[str])->list[dict[str,Any]]:
    return [{"path":path,"physical_sha256":_sha(safe.read(path)),"bytes":len(safe.read(path))} for path in paths]
def execute(root_path:Path=ROOT,*,ready:ReadyPreflight|None=None,opener:Callable[[Spec],HttpResponse]|None=None,capability:Any=None)->dict[str,Any]:
    session = _session_for(capability, root_path, "READY_PERSISTED", "EXECUTION_STARTED")
    try:
        if _is_workspace_root(root_path) and opener is not None:
            raise SD0Error("WAIT_DATA_NO_FALLBACK", "production opener injection forbidden")
        if ready is None:
            raise SD0Error("WAIT_DATA_NO_FALLBACK","READY required")
        snapshot,expected_context=_ready_snapshot(ready,session)
        safe=SafeRoot(root_path)
    except BaseException:
        with _CAPABILITY_LOCK: session.state = "CONSUMED_OR_INVALIDATED"
        raise
    request_fd=header_fd=None
    try:
        contract,plan,specs=_load(safe)
        try: persisted=safe.read(PREFLIGHT_PATH)
        except SD0Error as exc: raise SD0Error("WAIT_DATA_NO_FALLBACK","persisted READY missing") from exc
        if persisted != snapshot+b"\n" or _strict_json(snapshot).get("request_plan_sha256")!=plan["plan_sha256"]: raise SD0Error("WAIT_DATA_NO_FALLBACK","READY persistence/binding")
        if any(safe.exists_or_link(path) for path in NETWORK_PATHS): raise SD0Error("FAIL_CLOSED_NO_OVERWRITE", "runtime output already exists")
        if _issuing_context(safe,root_path,contract,plan,require_preflight_absent=False)!=expected_context: raise SD0Error("WAIT_DATA_NO_FALLBACK","issuing context drift")
        _stage_revalidate(session, root_path, "EXECUTION_STARTED", ready)
        budget=Budget(plan["resource_caps"]["maximum_total_local_artifact_bytes"],len(persisted))
        request_fd=budget.create(safe,NETWORK_PATHS[0],b"",append=True)
        _stage_revalidate(session, root_path, "EXECUTION_STARTED", ready)
        header_fd=budget.create(safe,NETWORK_PATHS[1],b"",append=True)
        run=ready.document["run_id"]; total=0; accepted={}; accepted_headers={}; opened=opener or StdlibProxyOpener(); start=time.monotonic(); failure=None
        def seal(caught: BaseException, spec: Spec, stamp: str, mono: int, record: dict[str,Any] | None, header: dict[str,Any] | None) -> str:
            if isinstance(caught,(MemoryError,KeyboardInterrupt,SystemExit,GeneratorExit)) or not isinstance(caught,Exception):
                raise caught
            if isinstance(caught,(SD0Error,socket.timeout,TimeoutError,ssl.SSLError,ConnectionError,OSError,http.client.HTTPException)):
                exc=caught if isinstance(caught,SD0Error) else SD0Error("WAIT_DATA_NO_FALLBACK","pre-response transport failure")
                state=exc.state
            elif isinstance(caught,Exception):
                exc=caught; state="STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE"
            if record is None:
                record={"run_id":run,"request_id":spec.request_id,"method":spec.method,"exact_url":spec.url,"hostname":urlsplit(spec.url).hostname,"proxy_endpoint":PROXY,"started_at_utc":stamp,"finished_at_utc":_now(),"elapsed_monotonic_ns":time.monotonic_ns()-mono,"status_code":None,"redirect_count":0,"declared_content_length":None,"response_body_bytes":0,"response_body_sha256":_sha(b""),"response_headers_sha256":_sha(b""),"tls_validation_result":"UNAVAILABLE","client_version":CLIENT_VERSION,"error_class":exc.__class__.__name__,"terminal_disposition":state}
            else:
                record["error_class"]=record["error_class"] or exc.__class__.__name__; record["terminal_disposition"]=state
            if header is not None:
                header["terminal_disposition"]=state
                _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
                _schema(contract,"WRITE_ONCE_RESPONSE_METADATA_LEDGER",header); budget.append(safe,header_fd,_canon(header)+b"\n")
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            _schema(contract,"WRITE_ONCE_LOGICAL_REQUEST_LEDGER",record); budget.append(safe,request_fd,_canon(record)+b"\n")
            return state
        for spec in specs:
            stamp,mono=_now(),time.monotonic_ns(); record=header=None
            if time.monotonic()-start>120: raise SD0Error("HALT_RESOURCE_CAP","wall clock")
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            response=None; opener_error=None
            try:
                response=opened(spec)
            except BaseException as caught:
                opener_error=caught
            # The callback may have changed authority/session state even when
            # it returned or raised.  This check is outside response sealing.
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            if opener_error is not None:
                failure=seal(opener_error,spec,stamp,mono,None,None); break
            process_error=None
            try:
                record,header,state=_make_observation(spec,response,total,stamp,mono); record["run_id"]=run
                if header is not None: header["run_id"]=run
                if state: raise SD0Error(state,"response failed")
                if spec.request_id=="SD0-006": _checksum(response.body)
                if time.monotonic()-start>120: raise SD0Error("HALT_RESOURCE_CAP","wall clock")
            except BaseException as caught:
                process_error=caught
            if process_error is not None:
                failure=seal(process_error,spec,stamp,mono,record,header); break
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            _schema(contract,"WRITE_ONCE_RESPONSE_METADATA_LEDGER",header); budget.append(safe,header_fd,_canon(header)+b"\n")
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            _schema(contract,"WRITE_ONCE_LOGICAL_REQUEST_LEDGER",record); budget.append(safe,request_fd,_canon(record)+b"\n")
            total+=len(response.body); accepted[spec.request_id]=response.body; accepted_headers[spec.request_id]=(record,header)
            path={"SD0-002":NETWORK_PATHS[2],"SD0-004":NETWORK_PATHS[3],"SD0-006":NETWORK_PATHS[4]}.get(spec.request_id)
            if path:
                _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
                fd=budget.create(safe,path,response.body); os.close(fd)
        head_path=None; checksum_result=None; zip_result=None
        if failure is None:
            checksum_result={"request_id":"SD0-006","zip_basename":"BTCUSDT-1m-2024-03.zip","sha256":_checksum(accepted["SD0-006"])}
            zip_record,zip_header=accepted_headers["SD0-007"]
            head={"schema_version":"pitar1-sd0-zip-head.v1","run_id":run,"request_id":"SD0-007","exact_url":zip_record["exact_url"],"method":"HEAD","status_code":zip_record["status_code"],"content_type":zip_header["content_type"],"declared_content_length":zip_record["declared_content_length"],"response_body_bytes":zip_record["response_body_bytes"],"headers_sha256":zip_header["headers_sha256"],"received_at_utc":zip_header["received_at_utc"],"terminal_disposition":zip_record["terminal_disposition"],"head_receipt_sha256":""}
            head["head_receipt_sha256"]=_self("pitar1/sd0-zip-head/v1",head,"head_receipt_sha256"); _schema(contract,"ARCHIVE_HEADER_METADATA_ONLY",head)
            _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
            fd=budget.create(safe,NETWORK_PATHS[5],_canon(head)+b"\n"); os.close(fd); head_path=NETWORK_PATHS[5]; zip_result={"path":head_path,"head_receipt_sha256":head["head_receipt_sha256"]}
        document_paths=[path for path in NETWORK_PATHS[2:5] if safe.exists_or_link(path)]
        closure={"schema_version":"pitar1-sd0-closure-report.v1","run_id":run,"route_binding":plan["route_binding"],"preflight_sha256":ready.digest,"request_ledger_sha256":_sha(safe.readfd(request_fd)),"response_header_ledger_sha256":_sha(safe.readfd(header_fd)),"document_identities":_identities(safe,document_paths),"checksum_result":checksum_result,"zip_head_result":zip_result,"terms_disposition":"WAIT_DATA_TERMS_D0_DENIED" if failure is None else None,"lane_disposition":"HAR1_RECONSTRUCTED_ENGINEERING_EVIDENCE_ONLY","terminal_disposition":failure or "WAIT_DATA_TERMS_D0_DENIED","failure_state":failure,"maximum_positive_claim":"No market-row or ZIP body was accessed.","external_gate_required":True,"closure_report_sha256":""}
        closure["closure_report_sha256"]=_self("pitar1/sd0-closure-report/v1",closure,"closure_report_sha256"); _schema(contract,"FAIL_CLOSED_SD0_RESULT",closure)
        _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
        fd=budget.create(safe,NETWORK_PATHS[6],_canon(closure)+b"\n"); os.close(fd)
        created=[path for path in NETWORK_PATHS[:-1] if safe.exists_or_link(path)]
        inventory={"schema_version":"pitar1-sd0-artifact-inventory.v1","inventory_id":"pitar1-sd0-"+run,"run_id":run,"route_binding":plan["route_binding"],"artifact_identities":_identities(safe,created),"allowlist_match":True,"outside_allowlist_count":0,"market_row_body_artifact_count":0,"zip_body_artifact_count":0,"inventory_sha256":""}
        inventory["inventory_sha256"]=_self("pitar1/sd0-inventory/v1",inventory,"inventory_sha256"); _schema(contract,"CONTENT_IDENTITY_INVENTORY",inventory)
        _stage_revalidate(session,root_path,"EXECUTION_STARTED",ready)
        fd=budget.create(safe,NETWORK_PATHS[7],_canon(inventory)+b"\n"); os.close(fd)
        if failure: raise SD0Error(failure,"partial evidence sealed")
        return closure
    finally:
        if request_fd is not None: os.close(request_fd)
        if header_fd is not None: os.close(header_fd)
        safe.close()
        if session is not None:
            with _CAPABILITY_LOCK: session.state = "CONSUMED_OR_INVALIDATED"

def main(argv:Sequence[str]|None=None,*,capability:Any=None)->int:
    session = _session_for(capability, ROOT, "MINTED", "MINTED")
    try:
        parser=argparse.ArgumentParser(); parser.add_argument("--execute",action="store_true"); parser.add_argument("--tests-evidence",required=True); args=parser.parse_args(argv)
        evidence=_strict_json(Path(args.tests_evidence).read_bytes()); result=preflight(tests_evidence=evidence, capability=capability)
        if not isinstance(result,ReadyPreflight):
            print(json.dumps(result,sort_keys=True)); return 2
        persist_ready(ROOT,result,capability=capability)
        if not args.execute: print(json.dumps(result.document,sort_keys=True)); return 0
        print(json.dumps(execute(ready=result,capability=capability),sort_keys=True)); return 0
    except BaseException:
        with _CAPABILITY_LOCK:
            session.state = "CONSUMED_OR_INVALIDATED"
        raise
if __name__=="__main__": raise SystemExit(main())
