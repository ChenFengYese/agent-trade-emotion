"""Dormant HAR1R2 R2E-amended preflight executor and offline validators.

The executor has no default network or evidence-write path: only a future, self-
hashed activation can issue its one-use capability. That capability is a
trusted-process procedural gate, not a cryptographic boundary against hostile
code already executing in this Python process (which can use reflection or
monkeypatching). That limitation is explicit in the Sol activation decision.
"""

import base64
import datetime as dt
import hashlib
import json
import os
import signal
import stat
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import MappingProxyType

ROUTE_PHYSICAL_SHA256 = "1512149ca8f2f9df3fa66490636db9f0f3e340873087a8c989c5093eea1f2057"
ROUTE_CANONICAL_SHA256 = "6979a3ec4b2df46d81d48533ed3ed2147d78f68ec9595fe7bbb7a9a1d3beafa0"
R2D_ROUTE_PHYSICAL_SHA256 = "5bcd3feee3bd52f27d8c268a89504c06884eb5541568fccf2ab168f91dded8ae"
R2D_ROUTE_CANONICAL_SHA256 = "4099f69788265afda3cd98baf3ce2f02850269f8a7468c3270b1e37d5a982814"
R2E_ROUTE_PHYSICAL_SHA256 = "fbbb48fc700bc5258c9bfd049676896b2475990fff64bf879eedad811e61dc71"
R2E_ROUTE_CANONICAL_SHA256 = "666354ec75eaee6fcf02c7ccf7a31e542d091514812b0ffe9d4f7f66bb095884"
R2F_ROUTE_PHYSICAL_SHA256 = "cbe15f0883825148e2a93187b8faa7f96a7d9ff996fe1636f77d0fc3f928a517"
R2F_ROUTE_CANONICAL_SHA256 = "793c77dc38a4f310c78decdbde52461a2732ee6fad25e404a99a97209bb6103f"
ROUTE_ID = "HAR1R2_SOURCE_PREFLIGHT_STATIC_v1"
RUN_ID = "har1r2-source-preflight-20260729-v1"
CWD = "/Users/wt/Documents/agent-trade-emotion"
FROZEN_BRANCH = "codex/s0-research-foundation"
FROZEN_HEAD = "7ca3fc4f99a57f98217e703f222b295653ace87e"
ACTIVATION_STATE = "WAIT_SOL_R2_ACTIVATION"
PROXY = "http://127.0.0.1:7897"
FUTURE_REQUESTS = (
    (1, "GET", "https://www.binance.com/ja", 2097152),
    (2, "GET", "https://www.binance.com/ja/terms", 2097152),
    (3, "GET", "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", 1048576),
    (4, "HEAD", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip", 0),
    (5, "GET", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip.CHECKSUM", 512),
)


class ContractError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ContractError("non-finite JSON value: " + value)


def load_strict_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)


def _canonical(document):
    return json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_exact(actual, expected):
    """JSON equality that never aliases booleans, integers, or floats."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_json_exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_json_exact(left, right) for left, right in zip(actual, expected))
    return actual == expected


def canonical_sha256(document, digest_field, domain):
    copy = dict(document)
    if digest_field not in copy:
        raise ContractError("missing canonical self hash")
    claimed = copy.pop(digest_field)
    if not isinstance(claimed, str) or len(claimed) != 64 or any(char not in "0123456789abcdef" for char in claimed):
        raise ContractError("invalid canonical self hash")
    actual = hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical(copy)).hexdigest()
    if claimed is not None and claimed != actual:
        raise ContractError("canonical self hash mismatch")
    return actual


def strict_base64(value):
    if not isinstance(value, str):
        raise ContractError("base64 is not text")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise ContractError("invalid base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ContractError("noncanonical base64")
    return decoded


def _after_spaces(record, count):
    index = -1
    for _ in range(count):
        index = record.find(b" ", index + 1)
        if index < 0:
            raise ContractError("porcelain field count")
    path = record[index + 1:]
    if not path:
        raise ContractError("empty porcelain path")
    return path


def parse_porcelain_v2_z(raw):
    """Return a byte-preserving path projection from a complete porcelain-v2 -z stream."""
    if not isinstance(raw, bytes) or not raw.endswith(b"\0"):
        raise ContractError("missing terminal NUL")
    records = raw[:-1].split(b"\0")
    if any(b"\0" in record for record in records):
        raise ContractError("embedded NUL")
    projection, branch, head = [], None, None
    index = 0
    while index < len(records):
        record = records[index]
        if record.startswith(b"# "):
            try:
                text = record.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ContractError("non-ASCII branch header") from exc
            if text.startswith("# branch.head "):
                if branch is not None:
                    raise ContractError("duplicate branch.head header")
                branch = text[14:]
            elif text.startswith("# branch.oid "):
                if head is not None:
                    raise ContractError("duplicate branch.oid header")
                head = text[13:]
        elif record.startswith(b"1 "):
            projection.append({"record_index": index, "record_kind": "1", "path_ordinal": 0,
                               "path_bytes_base64": base64.b64encode(_after_spaces(record, 8)).decode("ascii")})
        elif record.startswith(b"2 "):
            if index + 1 >= len(records):
                raise ContractError("rename/copy original path missing")
            new_path = _after_spaces(record, 9)
            projection.append({"record_index": index, "record_kind": "2", "path_ordinal": 0,
                               "path_bytes_base64": base64.b64encode(new_path).decode("ascii")})
            index += 1
            if not records[index]:
                raise ContractError("empty rename/copy original path")
            projection.append({"record_index": index, "record_kind": "2", "path_ordinal": 1,
                               "path_bytes_base64": base64.b64encode(records[index]).decode("ascii")})
        elif record.startswith(b"u "):
            projection.append({"record_index": index, "record_kind": "u", "path_ordinal": 0,
                               "path_bytes_base64": base64.b64encode(_after_spaces(record, 10)).decode("ascii")})
        elif record.startswith(b"? ") or record.startswith(b"! "):
            if not record[2:]:
                raise ContractError("empty porcelain path")
            projection.append({"record_index": index, "record_kind": chr(record[0]), "path_ordinal": 0,
                               "path_bytes_base64": base64.b64encode(record[2:]).decode("ascii")})
        else:
            raise ContractError("unknown porcelain-v2 record")
        index += 1
    if branch is None or head is None:
        raise ContractError("required branch headers missing")
    return records, projection, branch, head


def validate_baseline(path: Path):
    doc = load_strict_json(path)
    required = {"schema_version", "route_id", "run_id", "cwd", "command_argv", "capture_started_at_utc",
                "capture_finished_at_utc", "branch", "head", "route_physical_sha256", "route_canonical_sha256",
                "raw_status_base64", "raw_status_sha256", "raw_status_byte_count", "nul_delimiter_count",
                "raw_record_count", "raw_records_base64_in_order", "path_projection", "canonical_self_digest", "baseline_sha256"}
    if set(doc) != required or doc["schema_version"] != "har1r2-baseline.v1":
        raise ContractError("baseline schema")
    if (doc["route_id"], doc["run_id"], doc["cwd"], doc["command_argv"]) != (ROUTE_ID, RUN_ID, CWD, ["git", "status", "--porcelain=v2", "--branch", "-z", "-uall"]):
        raise ContractError("baseline route binding")
    if (doc["route_physical_sha256"], doc["route_canonical_sha256"]) != (ROUTE_PHYSICAL_SHA256, ROUTE_CANONICAL_SHA256):
        raise ContractError("baseline route hashes")
    if doc["canonical_self_digest"] != {"domain_prefix_utf8": "msta-hed/har1r2-baseline/v1", "excluded_field": "baseline_sha256", "algorithm": "SHA-256_CANONICAL_JSON"}:
        raise ContractError("baseline self digest metadata")
    raw = strict_base64(doc["raw_status_base64"])
    records = [strict_base64(item) for item in doc["raw_records_base64_in_order"]]
    if b"\0".join(records) + b"\0" != raw:
        raise ContractError("raw record reassembly")
    if (len(raw), raw.count(b"\0"), len(records)) != (doc["raw_status_byte_count"], doc["nul_delimiter_count"], doc["raw_record_count"]):
        raise ContractError("baseline byte or record count")
    if hashlib.sha256(raw).hexdigest() != doc["raw_status_sha256"]:
        raise ContractError("baseline raw hash")
    parsed_records, projection, branch, head = parse_porcelain_v2_z(raw)
    if parsed_records != records or projection != doc["path_projection"]:
        raise ContractError("baseline path projection")
    if (branch, head) != (doc["branch"], doc["head"]):
        raise ContractError("raw branch and head")
    if (branch, head) != (FROZEN_BRANCH, FROZEN_HEAD):
        raise ContractError("frozen branch and head")
    for key in ("capture_started_at_utc", "capture_finished_at_utc"):
        if not isinstance(doc[key], str):
            raise ContractError("capture time type")
        try:
            dt.datetime.strptime(doc[key], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ContractError("noncanonical capture time") from exc
    if doc["capture_started_at_utc"] > doc["capture_finished_at_utc"]:
        raise ContractError("capture time order")
    return canonical_sha256(doc, "baseline_sha256", "msta-hed/har1r2-baseline/v1")


def _months(start, end):
    year, month = map(int, start.split("-")); end_year, end_month = map(int, end.split("-"))
    while (year, month) <= (end_year, end_month):
        yield f"{year:04d}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _manifest():
    objects = []
    for interval, start, end in (("1m", "2025-04", "2026-06"), ("4h", "2020-07", "2025-03")):
        for month in _months(start, end):
            stem = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/" + interval + "/BTCUSDT-" + interval + "-" + month + ".zip"
            objects.extend(({"interval": interval, "month": month, "kind": "ZIP", "url": stem, "download_authorized": False},
                            {"interval": interval, "month": month, "kind": "CHECKSUM", "url": stem + ".CHECKSUM", "download_authorized": False}))
    return objects


def validate_source_contract(path: Path):
    doc = load_strict_json(path)
    required = {"schema_version", "route_id", "route_physical_sha256", "route_canonical_sha256", "user_scope", "source", "source_terms", "object_manifest", "future_five_request_plan", "canonical_self_digest", "source_contract_sha256"}
    if set(doc) != required or doc["schema_version"] != "har1r2-source-contract.v1":
        raise ContractError("source schema")
    if doc["canonical_self_digest"] != {"domain_prefix_utf8": "msta-hed/har1r2-source-contract/v1", "digest_field": "source_contract_sha256", "algorithm": "SHA-256_CANONICAL_JSON"}:
        raise ContractError("source self digest metadata")
    if (doc.get("route_id"), doc.get("route_physical_sha256"), doc.get("route_canonical_sha256")) != (ROUTE_ID, ROUTE_PHYSICAL_SHA256, ROUTE_CANONICAL_SHA256):
        raise ContractError("source route binding")
    if doc.get("user_scope") != {"actor": "NATURAL_PERSON", "jurisdiction": "JP", "purpose": "INTERNAL_RESEARCH_AND_DERIVED_ANALYSIS", "redistribution": "NOT_REQUESTED"} or doc.get("source") != {"venue": "BINANCE", "product_family": "USD_M_FUTURES", "instrument_id": "BTCUSDT"}:
        raise ContractError("source scope")
    if doc.get("source_terms") != {"state": "PREFLIGHT_PENDING_NO_LEGAL_CONCLUSION", "permission": "DENIED_PENDING_NEW_SOL_REVIEW"}:
        raise ContractError("source terms")
    manifest = doc.get("object_manifest", {})
    if set(manifest) != {"ordering", "zip_objects", "checksum_objects", "all_download_authorized", "objects"}:
        raise ContractError("manifest schema")
    if (manifest.get("zip_objects"), manifest.get("checksum_objects"), manifest.get("all_download_authorized"), manifest.get("objects")) != (72, 72, False, _manifest()):
        raise ContractError("exact object manifest")
    expected_requests = [{"sequence": n, "method": m, "url": u, "body_cap_bytes": cap} for n, m, u, cap in FUTURE_REQUESTS]
    plan = doc.get("future_five_request_plan")
    if not isinstance(plan, dict) or set(plan) != {"proxy", "redirects", "retries", "concurrency", "request_timeout_seconds", "total_elapsed_cap_seconds", "zip_get_or_body", "market_row_read", "requests"}:
        raise ContractError("future request schema")
    if plan.get("requests") != expected_requests:
        raise ContractError("exact future request plan")
    for key, value in (("proxy", PROXY), ("redirects", 0), ("retries", 0), ("concurrency", 1), ("request_timeout_seconds", 20), ("total_elapsed_cap_seconds", 90), ("zip_get_or_body", False), ("market_row_read", False)):
        if plan.get(key) != value:
            raise ContractError("future request cap")
    return canonical_sha256(doc, "source_contract_sha256", "msta-hed/har1r2-source-contract/v1")


def validate_purge_plan(path: Path):
    doc = load_strict_json(path)
    required = {"schema_version", "route_id", "parameter_status", "maximum_lookback_days", "maximum_holding_days", "feature_history_policy", "role_end_purge_days", "role_windows_before_purge", "eligible_decision_windows_after_purge", "label_rule", "canonical_self_digest", "purge_plan_sha256"}
    if set(doc) != required or doc["schema_version"] != "har1r2-purge-plan.v1" or doc["canonical_self_digest"] != {"domain_prefix_utf8": "msta-hed/har1r2-purge-plan/v1", "digest_field": "purge_plan_sha256", "algorithm": "SHA-256_CANONICAL_JSON"}:
        raise ContractError("purge schema")
    before = [{"role": "DEVELOPMENT", "start_inclusive": "2025-07-01T00:00:00Z", "end_exclusive": "2026-01-01T00:00:00Z"}, {"role": "CALIBRATION", "start_inclusive": "2026-01-01T00:00:00Z", "end_exclusive": "2026-04-01T00:00:00Z"}, {"role": "LOCKED_HISTORICAL_HOLDOUT", "start_inclusive": "2026-04-01T00:00:00Z", "end_exclusive": "2026-07-01T00:00:00Z"}]
    after = [{"role": "DEVELOPMENT", "start_inclusive": "2025-07-01T00:00:00Z", "end_exclusive": "2025-12-25T00:00:00Z"}, {"role": "CALIBRATION", "start_inclusive": "2026-01-01T00:00:00Z", "end_exclusive": "2026-03-25T00:00:00Z"}, {"role": "LOCKED_HISTORICAL_HOLDOUT", "start_inclusive": "2026-04-01T00:00:00Z", "end_exclusive": "2026-06-24T00:00:00Z"}]
    if (doc.get("route_id"), doc.get("parameter_status"), doc.get("maximum_lookback_days"), doc.get("maximum_holding_days"), doc.get("feature_history_policy"), doc.get("role_end_purge_days"), doc.get("role_windows_before_purge"), doc.get("eligible_decision_windows_after_purge"), doc.get("label_rule")) != (ROUTE_ID, "UNVALIDATED_INITIAL_BOUNDARIES", 90, 7, "PAST_ONLY_EARLIER_ROLE_CARRY_IN", 7, before, after, "NO_LABEL_OR_MAXIMUM_HOLDING_WINDOW_MAY_CROSS_A_ROLE_END"):
        raise ContractError("exact purge plan")
    return canonical_sha256(doc, "purge_plan_sha256", "msta-hed/har1r2-purge-plan/v1")


def reject_existing_target(path: Path):
    anchor = path.anchor
    current = Path(anchor) if anchor else Path(".")
    for component in path.parent.parts[len(current.parts):]:
        current = current / component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as exc:
            raise ContractError("missing target parent") from exc
        if stat.S_ISLNK(mode):
            raise ContractError("symlink parent denied")
        if not stat.S_ISDIR(mode):
            raise ContractError("non-directory parent denied")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise ContractError("symlink target denied")
    if not stat.S_ISREG(mode):
        raise ContractError("nonregular target denied")
    raise ContractError("existing target denied")


def require_future_sol_r2_activation(*_args, **_kwargs):
    """The dormant default has no callback, write, or network side effect."""
    raise PermissionError("WAIT_SOL_R2_ACTIVATION: a future SOL decision is required")


class EvidenceDurabilityError(RuntimeError):
    """A write or fsync was not proven durable; the file is not sealed."""
    external_evidence_state = "UNSEALED_OR_PARTIAL"


class EvidenceCloseFailureAfterFsyncError(EvidenceDurabilityError):
    """Close failed after one or more fsynced records, requiring review."""
    external_evidence_state = "REVIEW_REQUIRED_CLOSE_ERROR"

    def __init__(self):
        super().__init__("EVIDENCE_CLOSE_FAILURE_AFTER_FSYNC")


class EvidenceReadbackValidationError(RuntimeError):
    """Post-close validation failed; no sealed classification may be made."""
    external_evidence_state = "UNSEALED_OR_REVIEW_REQUIRED"


class _DeadlineExceeded(TimeoutError):
    pass


class _PosixDeadline:
    """Interrupt a production request/read, but never an evidence write or fsync."""
    def __init__(self, seconds):
        self.seconds = seconds
        self.old_handler = None
        self.old_timer = None

    def _expired(self, _signum, _frame):
        raise _DeadlineExceeded("absolute request deadline exceeded")

    def __enter__(self):
        if threading.current_thread() is not threading.main_thread():
            raise ContractError("production deadline requires the main thread")
        if not isinstance(self.seconds, (int, float)) or not 0 < self.seconds <= 20:
            raise ContractError("invalid request deadline")
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
            raise ContractError("existing ITIMER_REAL denied before TCP")
        self.old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._expired)
        self.old_timer = signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, _type, _value, _traceback):
        signal.setitimer(signal.ITIMER_REAL, self.old_timer[0], self.old_timer[1])
        signal.signal(signal.SIGALRM, self.old_handler)
        return False


def _posix_deadline(seconds):
    """macOS/POSIX-only production deadline; called only around network response work."""
    return _PosixDeadline(seconds)


def _require_production_alarm_available():
    if threading.current_thread() is not threading.main_thread():
        raise ContractError("production deadline requires the main thread")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ContractError("existing ITIMER_REAL denied before TCP")


EVIDENCE_RELATIVE_PATH = "har1r2/evidence.jsonl"
EVIDENCE_SCHEMA_VERSION = "har1r2-preflight-evidence.v1"
_BASELINE_PHYSICAL = "8e4c9c7ad50eaa9061bbca6cd2c4e691628974da322faac3803222184df340d6"
_BASELINE_CANONICAL = "5873a0d363c2746799fbc8019cddd0af020e998013cea48e608838e4a05bbf2b"
_SOURCE_PHYSICAL = "87f23ab76b243341f26844f17ae582c502a3322943a241f2c94b3c110179df4b"
_SOURCE_CANONICAL = "42cd256a574f7ddeb1c8930c9ba4d43c4e177dadb1470eada832801cfb7dfafe"
_PURGE_PHYSICAL = "caeb09d8b756980fdcc9fca5998da978d26cbbafaa100ae186178962b6b09031"
_PURGE_CANONICAL = "a9d4d3ed55a1354613a3c641be6478372a692ddcb87077187e5e5f56e0e74c3f"
_ACTIVATION_FIELDS = {"decision_id", "permission", "issued_at_utc", "expires_at_utc", "bindings", "canonical_self_digest", "activation_sha256"}
_BINDING_FIELDS = {"r2_route_physical", "r2_route_canonical", "r2d_route_physical", "r2d_route_canonical", "r2e_route_physical", "r2e_route_canonical", "r2f_route_physical", "r2f_route_canonical", "baseline_physical", "baseline_canonical", "source_physical", "source_canonical", "purge_physical", "purge_canonical", "client_physical", "test_physical", "run_id", "evidence_path", "request_plan"}


def _utc(value):
    if not isinstance(value, str):
        raise ContractError("UTC timestamp type")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError as exc:
        raise ContractError("noncanonical UTC timestamp") from exc


def _utc_now(value):
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _physical(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _request_plan():
    return [{"sequence": sequence, "method": method, "url": url, "body_cap_bytes": cap} for sequence, method, url, cap in FUTURE_REQUESTS]


def _hex_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _parse_raw_activation(raw):
    """Strict production ingestion retaining the exact activation byte identity."""
    if type(raw) is not bytes:
        raise ContractError("activation input must be raw bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ContractError("activation UTF-8 BOM denied")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError("activation invalid UTF-8") from exc
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContractError("activation invalid JSON") from exc
    if not isinstance(document, dict):
        raise ContractError("activation top level must be an object")
    return document, hashlib.sha256(raw).hexdigest()


def _capability_factory():
    """Keep the construction token in this closure, never in module globals."""
    token = object()
    registry, issued_activations, registry_lock = {}, set(), threading.Lock()

    class IssuedCapability:
        __slots__ = ("_lock", "_used", "_bindings", "_expires", "_issued", "_pid", "_activation_sha256", "_activation_raw_physical_sha256", "_decision_id", "_permission")

        def __init__(self, supplied_token, bindings, issued, expires, activation_sha256, activation_raw_physical_sha256, decision_id, permission):
            if supplied_token is not token:
                raise PermissionError("capability issuer required")
            self._lock = threading.Lock()
            self._used = False
            # Canonical roundtrip breaks all aliases to the caller's activation
            # document, including nested request_plan dictionaries/lists.
            self._bindings = MappingProxyType(json.loads(_canonical(bindings).decode("utf-8")))
            self._issued = issued
            self._expires = expires
            self._pid = os.getpid()
            self._activation_sha256 = activation_sha256
            self._activation_raw_physical_sha256 = activation_raw_physical_sha256
            self._decision_id = decision_id
            self._permission = permission

        def __copy__(self):
            raise PermissionError("opaque capability")

        def __deepcopy__(self, _memo):
            raise PermissionError("opaque capability")

        def __reduce__(self):
            raise PermissionError("opaque capability")

    def issue(raw_activation, now=None):
        """Validate raw activation bytes and register one capability without side effects."""
        document, activation_raw_physical = _parse_raw_activation(raw_activation)
        if set(document) != _ACTIVATION_FIELDS:
            raise ContractError("activation schema")
        if document.get("decision_id") != "SOL_HAR1R2_SOURCE_PREFLIGHT_ACTIVATION.v1" or document.get("permission") != "ONE_BOUNDED_FIVE_REQUEST_PREFLIGHT":
            raise ContractError("activation permission")
        if document.get("canonical_self_digest") != {"domain_prefix_utf8": "msta-hed/har1r2-activation/v1", "digest_field": "activation_sha256", "algorithm": "SHA-256_CANONICAL_JSON"}:
            raise ContractError("activation digest metadata")
        activation = canonical_sha256(document, "activation_sha256", "msta-hed/har1r2-activation/v1")
        issued, expires = _utc(document["issued_at_utc"]), _utc(document["expires_at_utc"])
        current = time.time() if now is None else now
        if not 0 < expires - issued <= 900:
            raise ContractError("activation TTL")
        if not isinstance(current, (int, float)) or isinstance(current, bool) or issued > current or current > expires:
            raise ContractError("activation time window")
        bindings = document.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
            raise ContractError("activation bindings")
        expected = {"r2_route_physical": ROUTE_PHYSICAL_SHA256, "r2_route_canonical": ROUTE_CANONICAL_SHA256,
                    "r2d_route_physical": R2D_ROUTE_PHYSICAL_SHA256, "r2d_route_canonical": R2D_ROUTE_CANONICAL_SHA256,
                    "r2e_route_physical": R2E_ROUTE_PHYSICAL_SHA256, "r2e_route_canonical": R2E_ROUTE_CANONICAL_SHA256,
                    "r2f_route_physical": R2F_ROUTE_PHYSICAL_SHA256, "r2f_route_canonical": R2F_ROUTE_CANONICAL_SHA256,
                    "baseline_physical": _BASELINE_PHYSICAL, "baseline_canonical": _BASELINE_CANONICAL,
                    "source_physical": _SOURCE_PHYSICAL, "source_canonical": _SOURCE_CANONICAL,
                    "purge_physical": _PURGE_PHYSICAL, "purge_canonical": _PURGE_CANONICAL,
                    "run_id": RUN_ID, "evidence_path": EVIDENCE_RELATIVE_PATH, "request_plan": _request_plan()}
        for key, value in expected.items():
            if key not in bindings or not _json_exact(bindings[key], value):
                raise ContractError("activation binding: " + key)
        if not _hex_digest(bindings["client_physical"]) or not _hex_digest(bindings["test_physical"]):
            raise ContractError("activation final file hash")
        with registry_lock:
            if activation in issued_activations:
                raise PermissionError("activation already issued in this process")
            cap = IssuedCapability(token, bindings, issued, expires, activation, activation_raw_physical, document["decision_id"], document["permission"])
            issued_activations.add(activation)
            registry[id(cap)] = cap
        return cap

    def consume(capability, now):
        if type(capability) is not IssuedCapability or capability._pid != os.getpid():
            raise PermissionError("foreign capability")
        with registry_lock:
            if registry.get(id(capability)) is not capability:
                raise PermissionError("unissued capability")
        with capability._lock:
            if capability._used or not capability._issued <= now <= capability._expires:
                raise PermissionError("capability reused, premature, or expired")
            capability._used = True

    return IssuedCapability, issue, consume


_Capability, issue_activation_capability, _consume_capability = _capability_factory()


def _validate_r2_route(path):
    document = load_strict_json(path)
    if document.get("schema_version") != "sol-har1-btcusdt-source-preflight-r2-route.v1" or document.get("decision_id") != "SOL_HAR1_BTCUSDT_SOURCE_PREFLIGHT_R2_ROUTE.v1":
        raise ContractError("R2 route identity")
    return canonical_sha256(document, "decision_sha256", "msta-hed/sol-har1-btcusdt-source-preflight-r2-route/v1")


def _validate_r2d_route(path):
    document = load_strict_json(path)
    if document.get("schema_version") != "sol-har1-btcusdt-source-preflight-r2d-route-amendment.v1" or document.get("decision_id") != "SOL_HAR1_BTCUSDT_SOURCE_PREFLIGHT_R2D_ROUTE_AMENDMENT.v1":
        raise ContractError("R2D route identity")
    return canonical_sha256(document, "decision_sha256", "msta-hed/sol-har1-btcusdt-source-preflight-r2d-route-amendment/v1")


def _validate_r2e_route(path):
    document = load_strict_json(path)
    if document.get("schema_version") != "sol-har1-btcusdt-source-preflight-r2e-route-amendment.v1" or document.get("decision_id") != "SOL_HAR1_BTCUSDT_SOURCE_PREFLIGHT_R2E_ROUTE_AMENDMENT.v1":
        raise ContractError("R2E route identity")
    predecessor = document.get("predecessor_bindings")
    if not isinstance(predecessor, dict) or predecessor.get("r2_route") != {"path": "config/sol_decision.har1-btcusdt-source-preflight-r2-route.v1.json", "physical_sha256": ROUTE_PHYSICAL_SHA256, "canonical_sha256": ROUTE_CANONICAL_SHA256} or predecessor.get("r2d_route") != {"path": "config/sol_decision.har1-btcusdt-source-preflight-r2d-route-amendment.v1.json", "physical_sha256": R2D_ROUTE_PHYSICAL_SHA256, "canonical_sha256": R2D_ROUTE_CANONICAL_SHA256}:
        raise ContractError("R2E predecessor binding")
    return canonical_sha256(document, "decision_sha256", "msta-hed/sol-har1-btcusdt-source-preflight-r2e-route-amendment/v1")


def _validate_r2f_route(path):
    document = load_strict_json(path)
    if document.get("schema_version") != "sol-har1-btcusdt-source-preflight-r2f-route-amendment.v1" or document.get("decision_id") != "SOL_HAR1_BTCUSDT_SOURCE_PREFLIGHT_R2F_ROUTE_AMENDMENT.v1":
        raise ContractError("R2F route identity")
    predecessor = document.get("predecessor_bindings")
    expected = {
        "r2_route": {"path": "config/sol_decision.har1-btcusdt-source-preflight-r2-route.v1.json", "physical_sha256": ROUTE_PHYSICAL_SHA256, "canonical_sha256": ROUTE_CANONICAL_SHA256},
        "r2d_route": {"path": "config/sol_decision.har1-btcusdt-source-preflight-r2d-route-amendment.v1.json", "physical_sha256": R2D_ROUTE_PHYSICAL_SHA256, "canonical_sha256": R2D_ROUTE_CANONICAL_SHA256},
        "r2e_route": {"path": "config/sol_decision.har1-btcusdt-source-preflight-r2e-route-amendment.v1.json", "physical_sha256": R2E_ROUTE_PHYSICAL_SHA256, "canonical_sha256": R2E_ROUTE_CANONICAL_SHA256},
    }
    if not isinstance(predecessor, dict) or any(not _json_exact(predecessor.get(key), value) for key, value in expected.items()):
        raise ContractError("R2F predecessor binding")
    return canonical_sha256(document, "decision_sha256", "msta-hed/sol-har1-btcusdt-source-preflight-r2f-route-amendment/v1")


def _pre_tcp_recheck(capability):
    """Recheck every physical and canonical activation binding before any TCP work."""
    bindings = capability._bindings
    if not _json_exact(bindings.get("request_plan"), _request_plan()):
        raise ContractError("frozen request plan drift")
    root = Path(__file__).resolve().parent.parent
    physical = ((root / "config/sol_decision.har1-btcusdt-source-preflight-r2-route.v1.json", "r2_route_physical", ROUTE_PHYSICAL_SHA256),
                (root / "config/sol_decision.har1-btcusdt-source-preflight-r2d-route-amendment.v1.json", "r2d_route_physical", R2D_ROUTE_PHYSICAL_SHA256),
                (root / "config/sol_decision.har1-btcusdt-source-preflight-r2e-route-amendment.v1.json", "r2e_route_physical", R2E_ROUTE_PHYSICAL_SHA256),
                (root / "config/sol_decision.har1-btcusdt-source-preflight-r2f-route-amendment.v1.json", "r2f_route_physical", R2F_ROUTE_PHYSICAL_SHA256),
                (Path(__file__).with_name("baseline.json"), "baseline_physical", _BASELINE_PHYSICAL),
                (Path(__file__).with_name("source_contract.json"), "source_physical", _SOURCE_PHYSICAL),
                (Path(__file__).with_name("purge_plan.json"), "purge_physical", _PURGE_PHYSICAL),
                (Path(__file__), "client_physical", bindings["client_physical"]),
                (Path(__file__).with_name("test_preflight_client.py"), "test_physical", bindings["test_physical"]))
    for path, name, expected in physical:
        if _physical(path) != expected or bindings[name] != expected:
            raise ContractError("physical drift: " + name)
    canonical = ((_validate_r2_route(root / "config/sol_decision.har1-btcusdt-source-preflight-r2-route.v1.json"), "r2_route_canonical", ROUTE_CANONICAL_SHA256),
                 (_validate_r2d_route(root / "config/sol_decision.har1-btcusdt-source-preflight-r2d-route-amendment.v1.json"), "r2d_route_canonical", R2D_ROUTE_CANONICAL_SHA256),
                 (_validate_r2e_route(root / "config/sol_decision.har1-btcusdt-source-preflight-r2e-route-amendment.v1.json"), "r2e_route_canonical", R2E_ROUTE_CANONICAL_SHA256),
                 (_validate_r2f_route(root / "config/sol_decision.har1-btcusdt-source-preflight-r2f-route-amendment.v1.json"), "r2f_route_canonical", R2F_ROUTE_CANONICAL_SHA256),
                 (validate_baseline(Path(__file__).with_name("baseline.json")), "baseline_canonical", _BASELINE_CANONICAL),
                 (validate_source_contract(Path(__file__).with_name("source_contract.json")), "source_canonical", _SOURCE_CANONICAL),
                 (validate_purge_plan(Path(__file__).with_name("purge_plan.json")), "purge_canonical", _PURGE_CANONICAL))
    for actual, name, expected in canonical:
        if actual != expected or bindings[name] != expected:
            raise ContractError("canonical drift: " + name)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class _ForcedHttpsProxyHandler(urllib.request.ProxyHandler):
    """Unlike ProxyHandler, this deliberately never calls proxy_bypass()."""
    def __init__(self):
        super().__init__({"https": PROXY})

    def proxy_open(self, request, proxy, protocol):
        if protocol != "https" or proxy != PROXY:
            raise ContractError("fixed HTTPS proxy required")
        request.set_proxy("127.0.0.1:7897", "https")
        return None


def _build_production_opener():
    return urllib.request.build_opener(_ForcedHttpsProxyHandler(), _NoRedirect())


_PRODUCTION_HEADERS = {"Accept-Encoding": "identity", "Connection": "close", "User-Agent": "agent-trade-emotion-har1-source-preflight/1.0"}


def _production_request(method, url):
    return urllib.request.Request(url, method=method, headers=_PRODUCTION_HEADERS)


def _activation_record(capability, recorded_at):
    """The durable first line binds later request records to the activation."""
    return {"schema_version": EVIDENCE_SCHEMA_VERSION, "record_type": "ACTIVATION", "terminal": False,
            "activation_sha256": capability._activation_sha256,
            "activation_raw_physical_sha256": capability._activation_raw_physical_sha256,
            "decision_id": capability._decision_id,
            "permission": capability._permission, "issued_at_utc": _utc_now(capability._issued),
            "expires_at_utc": _utc_now(capability._expires), "bindings": dict(capability._bindings),
            "run_id": capability._bindings["run_id"], "proxy": PROXY,
            "request_headers": dict(_PRODUCTION_HEADERS), "request_plan": _request_plan(),
            "recorded_at_utc": _utc_now(recorded_at)}


def run_preflight(capability):
    """The only production transport entry point; it accepts no transport or opener injection."""
    _consume_capability(capability, time.time())
    _pre_tcp_recheck(capability)
    _require_production_alarm_available()
    opener = _build_production_opener()  # Building handlers performs no TCP work.
    writer = _EvidenceWriter(Path(__file__).with_name("evidence.jsonl"))
    writer.prepare()  # O_EXCL/no-follow must succeed before the first transport call.
    try:
        _durable_write(writer, _activation_record(capability, time.time()))
        protocol_success = _run_with_transport(capability, lambda method, url, timeout: opener.open(_production_request(method, url), timeout=timeout), writer, time.monotonic, time.time, _posix_deadline)
    except BaseException:
        # Preserve a write/fsync failure: a later close error cannot upgrade or
        # replace the fact that a record's durability was never established.
        try:
            _durable_close(writer)
        except EvidenceCloseFailureAfterFsyncError:
            pass
        raise
    else:
        _durable_close(writer)
        return _readback_sealed_evidence(writer.path, capability, protocol_success)


class _EvidenceWriter:
    def __init__(self, path):
        self.path, self.fd, self.prev = Path(path), None, "0" * 64

    def prepare(self):
        if self.fd is not None:
            return
        reject_existing_target(self.path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = None
        try:
            directory_fd = os.open(str(self.path.parent), directory_flags)
            self.fd = os.open(self.path.name, flags, 0o600, dir_fd=directory_fd)
            if not stat.S_ISREG(os.fstat(self.fd).st_mode):
                raise ContractError("nonregular evidence target")
        except FileExistsError as exc:
            raise ContractError("existing evidence target") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def write(self, record):
        if self.fd is None:
            self.prepare()
        line = _canonical(dict(record, previous_sha256=self.prev)) + b"\n"
        offset = 0
        try:
            while offset < len(line):
                written = os.write(self.fd, line[offset:])
                if written <= 0:
                    raise OSError("short evidence write")
                offset += written
            os.fsync(self.fd)
        except OSError as exc:
            raise EvidenceDurabilityError("EVIDENCE_DURABILITY_FAILURE") from exc
        self.prev = hashlib.sha256(line).hexdigest()

    def close(self):
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            os.close(fd)
        except OSError as exc:
            raise EvidenceCloseFailureAfterFsyncError() from exc


def _durable_write(writer, record):
    """Never retry or attempt a terminal upgrade after an evidence failure."""
    try:
        writer.write(record)
    except EvidenceDurabilityError:
        raise
    except Exception as exc:
        raise EvidenceDurabilityError("EVIDENCE_DURABILITY_FAILURE") from exc


def _durable_close(writer):
    try:
        writer.close()
    except EvidenceCloseFailureAfterFsyncError:
        raise
    except Exception as exc:
        raise EvidenceCloseFailureAfterFsyncError() from exc


def _readback_records(raw, capability):
    """Validate only the immutable bytes already closed by the writer."""
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise EvidenceReadbackValidationError("invalid JSONL framing")
    lines = raw[:-1].split(b"\n")
    if not lines or any(not line for line in lines):
        raise EvidenceReadbackValidationError("empty or extra JSONL record")
    records = []
    for line in lines:
        try:
            text = line.decode("utf-8", errors="strict")
            record = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ContractError) as exc:
            raise EvidenceReadbackValidationError("invalid strict JSONL record") from exc
        if not isinstance(record, dict):
            raise EvidenceReadbackValidationError("JSONL record is not an object")
        records.append(record)
    if records[0].get("record_type") != "ACTIVATION" or records[0].get("terminal") is not False:
        raise EvidenceReadbackValidationError("activation is not first")
    if sum(record.get("record_type") == "ACTIVATION" for record in records) != 1:
        raise EvidenceReadbackValidationError("activation is not unique")
    activation = records[0]
    scalar_identity = (activation.get("schema_version"), activation.get("activation_sha256"), activation.get("activation_raw_physical_sha256"), activation.get("decision_id"), activation.get("permission"), activation.get("run_id"), activation.get("proxy"))
    expected_scalar_identity = (EVIDENCE_SCHEMA_VERSION, capability._activation_sha256, capability._activation_raw_physical_sha256, capability._decision_id, capability._permission, capability._bindings["run_id"], PROXY)
    if scalar_identity != expected_scalar_identity or not _json_exact(activation.get("bindings"), dict(capability._bindings)) or not _json_exact(activation.get("request_plan"), _request_plan()):
        raise EvidenceReadbackValidationError("activation binding drift")
    previous = "0" * 64
    for line, record in zip(lines, records):
        if record.get("previous_sha256") != previous:
            raise EvidenceReadbackValidationError("raw-line hash chain mismatch")
        previous = hashlib.sha256(line + b"\n").hexdigest()
    terminal_indices = [index for index, record in enumerate(records) if record.get("terminal") is True]
    if terminal_indices != [len(records) - 1]:
        raise EvidenceReadbackValidationError("terminal must be unique and last")
    terminal = records[-1]
    if terminal.get("record_type") != "TERMINAL" or terminal.get("outcome") not in {"SUCCESS", "FAILURE"}:
        raise EvidenceReadbackValidationError("terminal outcome")
    expected_sequence = 1
    for index, record in enumerate(records[1:], start=1):
        if expected_sequence > len(FUTURE_REQUESTS):
            raise EvidenceReadbackValidationError("too many protocol records")
        if record.get("schema_version") != EVIDENCE_SCHEMA_VERSION or not _json_exact(record.get("sequence"), expected_sequence):
            raise EvidenceReadbackValidationError("frozen sequence drift")
        _, method, url, _body_cap = FUTURE_REQUESTS[expected_sequence - 1]
        if record.get("method") != method or record.get("url") != url:
            raise EvidenceReadbackValidationError("frozen request drift")
        is_last = index == len(records) - 1
        if not is_last and (record.get("record_type") != "REQUEST" or record.get("terminal") is not False or record.get("outcome") != "SUCCESS"):
            raise EvidenceReadbackValidationError("nonterminal protocol record")
        expected_sequence += 1
    if terminal["outcome"] == "SUCCESS" and not _json_exact(terminal.get("sequence"), len(FUTURE_REQUESTS)):
        raise EvidenceReadbackValidationError("success terminal sequence")
    return terminal["outcome"]


def _readback_sealed_evidence(path, capability, protocol_success=None):
    """Read once with no-follow and no writes, then make the only sealed claim."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise EvidenceReadbackValidationError("nonregular evidence readback target")
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceReadbackValidationError("nonregular evidence readback target")
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(fd)
    except EvidenceReadbackValidationError:
        raise
    except OSError as exc:
        raise EvidenceReadbackValidationError("readback open/read failure") from exc
    outcome = _readback_records(b"".join(chunks), capability)
    if protocol_success is not None and (protocol_success is not (outcome == "SUCCESS")):
        raise EvidenceReadbackValidationError("protocol outcome mismatch")
    return {"external_evidence_state": "SEALED", "protocol_outcome": outcome, "terminal_reliable": True}


def _headers(response):
    headers = getattr(response, "headers", {}) or {}
    names = ("Content-Length", "Content-Type", "Last-Modified", "ETag", "Strict-Transport-Security", "Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy")
    return {name: headers.get(name) for name in names if headers.get(name) is not None}


def _failure_headers(response):
    headers = _headers(response)
    source = getattr(response, "headers", {}) or {}
    for name in ("Location", "Date"):
        if source.get(name) is not None:
            headers[name] = source.get(name)
    return headers


def _response_status(response):
    return getattr(response, "status", getattr(response, "code", None))


def _close_response(response):
    close = getattr(response, "close", None)
    if close is not None:
        close()


def _run_with_transport(capability, transport, writer, clock, wall_clock=time.time, deadline_factory=None):
    """Test-only seam. Production uses run_preflight and cannot inject an opener or transport."""
    del capability  # Its registry and one-use validation are performed by run_preflight.
    network_elapsed = 0.0
    for sequence, method, url, body_cap in FUTURE_REQUESTS:
        response, body, status, response_headers, attempted = None, None, None, {}, False
        request_elapsed, request_accounted = 0.0, False
        request_started = wall_clock()
        request_clock = clock()
        try:
            elapsed_before = network_elapsed
            if elapsed_before >= 90:
                raise TimeoutError("total elapsed cap before request")
            remaining = 90 - elapsed_before
            timeout = min(20, remaining)
            if deadline_factory is None:
                attempted = True
                response = transport(method, url, timeout)
                status = _response_status(response)
                response_headers = _headers(response)
                body = response.read(body_cap + 1)
                _close_response(response)
                response = None
            else:
                # The deadline is deliberately disarmed before writer.write/fsync.
                with deadline_factory(timeout):
                    attempted = True
                    response = transport(method, url, timeout)
                    status = _response_status(response)
                    response_headers = _headers(response)
                    body = response.read(body_cap + 1)
                    _close_response(response)
                    response = None
            request_elapsed = max(0.0, clock() - request_clock)
            elapsed_after = network_elapsed + request_elapsed
            if elapsed_after >= 90:
                raise TimeoutError("total elapsed cap after request")
            network_elapsed = elapsed_after
            request_accounted = True
            if status != 200:
                raise ContractError("unexpected HTTP status")
            if len(body) > body_cap or (method == "HEAD" and body):
                raise ContractError("body cap")
            checksum = None
            if sequence == 5:
                checksum = body.strip().split()
                if len(checksum) != 2 or checksum[1] != b"BTCUSDT-1m-2025-07.zip" or len(checksum[0]) != 64 or any(byte not in b"0123456789abcdefABCDEF" for byte in checksum[0]):
                    raise ContractError("checksum")
            completed = wall_clock()
            record = {"schema_version": EVIDENCE_SCHEMA_VERSION, "record_type": "TERMINAL" if sequence == len(FUTURE_REQUESTS) else "REQUEST",
                      "sequence": sequence, "method": method, "url": url, "status_code": status,
                      "response_bytes": len(body), "body_base64": base64.b64encode(body).decode("ascii"),
                      "body_sha256": hashlib.sha256(body).hexdigest(), "request_started_at_utc": _utc_now(request_started),
                      "response_completed_at_utc": _utc_now(completed), "request_elapsed_ms": int(request_elapsed * 1000),
                      "cumulative_elapsed_ms": int(network_elapsed * 1000), "concurrency": 1,
                      "security_headers": response_headers, "request_attempted": True,
                      "terminal": sequence == len(FUTURE_REQUESTS), "outcome": "SUCCESS"}
            # Preserve headers before close without retaining a network response object.
            if checksum is not None:
                record["checksum_sha256"] = checksum[0].decode("ascii").lower()
                record["checksum_basename"] = checksum[1].decode("ascii")
            _durable_write(writer, record)
        except EvidenceDurabilityError:
            raise
        except Exception as exc:
            try:
                error_name, body_capture_state = type(exc).__name__, None
                error_response = response
                http_error_body = error_response is None and isinstance(exc, urllib.error.HTTPError)
                if http_error_body:
                    error_response = exc
                if error_response is not None:
                    status = _response_status(error_response)
                    response_headers = _failure_headers(error_response)
                    # A normal read failure must not be retried. HTTPError is the
                    # sole case where urllib raised before exposing a response.
                    if http_error_body and body is None:
                        def capture_http_error_body():
                            nonlocal body
                            try:
                                body = error_response.read(body_cap + 1)
                            finally:
                                _close_response(error_response)
                        if deadline_factory is None:
                            try:
                                capture_http_error_body()
                            except Exception as capture_error:
                                body_capture_state, error_name = "READ_OR_CLOSE_FAILED", type(capture_error).__name__
                        else:
                            current_request_elapsed = max(0.0, clock() - request_clock)
                            capture_budget = min(20 - current_request_elapsed, 90 - (network_elapsed + current_request_elapsed))
                            if capture_budget <= 0:
                                body_capture_state = "NOT_CAPTURED_DEADLINE_EXHAUSTED"
                                try:
                                    _close_response(error_response)
                                except Exception:
                                    pass
                            else:
                                try:
                                    # The original request deadline is absolute:
                                    # only its still-unspent request/total budget
                                    # may be used for an HTTPError body and close.
                                    with deadline_factory(capture_budget):
                                        capture_http_error_body()
                                except Exception as capture_error:
                                    body_capture_state, error_name = "READ_OR_CLOSE_FAILED", type(capture_error).__name__
                    else:
                        try:
                            _close_response(error_response)
                        except Exception:
                            pass
                    response = None
                if response is not None:
                    status = _response_status(response)
                    _close_response(response)
                    response = None
                completed = wall_clock()
                if request_accounted:
                    failed_request_elapsed, failed_cumulative_elapsed = request_elapsed, network_elapsed
                else:
                    failed_request_elapsed = max(0.0, clock() - request_clock) if attempted else 0.0
                    failed_cumulative_elapsed = network_elapsed + failed_request_elapsed
                record = {"schema_version": EVIDENCE_SCHEMA_VERSION, "record_type": "TERMINAL", "sequence": sequence,
                          "method": method, "url": url, "request_started_at_utc": _utc_now(request_started),
                          "response_completed_at_utc": _utc_now(completed), "request_elapsed_ms": int(failed_request_elapsed * 1000),
                          "cumulative_elapsed_ms": int(failed_cumulative_elapsed * 1000), "concurrency": 1,
                          "terminal": True, "outcome": "FAILURE", "error": error_name, "request_attempted": attempted}
                if status is not None:
                    record["status_code"] = status
                if body is not None:
                    record["response_bytes"] = len(body)
                    record["body_sha256"] = hashlib.sha256(body).hexdigest()
                    record["body_base64"] = base64.b64encode(body).decode("ascii")
                if response_headers:
                    record["response_headers"] = response_headers
                if body_capture_state is not None:
                    record["body_capture_state"] = body_capture_state
                _durable_write(writer, record)
            except EvidenceDurabilityError:
                raise
            except Exception as durability:
                raise EvidenceDurabilityError("EVIDENCE_DURABILITY_FAILURE") from durability
            return False
        finally:
            if response is not None:
                try:
                    _close_response(response)
                except Exception:
                    pass
    return True
