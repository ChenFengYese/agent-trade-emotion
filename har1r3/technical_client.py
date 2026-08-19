"""Dormant HAR1R3 technical reachability client.

This module defines a new R3 activation, capability, run and evidence namespace.
It does not reuse the closed R2 capability, run or evidence output.  Selected R2
parsing/deadline utilities are imported read-only only after the final R2 client
physical hash is verified.
"""

import base64
import hashlib
import json
import os
import stat
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import MappingProxyType, ModuleType

R3_ROUTE_PHYSICAL_SHA256 = "6b23ca9248233929023b29c606466af7063929e23fe70e89d01e0f1b2fca8c8d"
R3_ROUTE_CANONICAL_SHA256 = "a21411873c7a793dc9d51983c4717ac3afad422bfe0d4f744679e9a51673b604"
R2_CLIENT_PHYSICAL_SHA256 = "692facf25a70bdd33f214484329359554f4c920300003816e565086e1d51b7a7"
R2_ACTIVATION_PHYSICAL_SHA256 = "c1b4b3b68fe8787d36a7b08fe2b76cf679fca9e3785678e8bf751b41e7fbae18"
R2_ACTIVATION_CANONICAL_SHA256 = "784c864f23d604ed890d218229e5346d964fa8eda3d5b1e3ea8e61f48b35a897"
R2_EVIDENCE_PHYSICAL_SHA256 = "01a3705f0e4baf45082d01d5447b727638a5259ede63792eef4cd75033fbafbe"
TECHNICAL_PLAN_PHYSICAL_SHA256 = "34a3aea128c7f538d88572c224cac6710e498ee84fb099c49244e599e7300e4b"
TECHNICAL_PLAN_CANONICAL_SHA256 = "19c161282927712248cd0682b307dcb5bebcd5b8084d871ce3c173f86e52d7bc"
TERMS_CONTRACT_PHYSICAL_SHA256 = "0809b031cc722b3f3e1fab54f4f88a29c1a53609872270fb476c65f1ff7cec02"
TERMS_CONTRACT_CANONICAL_SHA256 = "71a8592d35f01c4667a0eaff555cfb43dd5e2b6c245f206f3ca76c0a2fd082af"


class ContractError(ValueError):
    """Bootstrap error used until the hash-bound R2 definition is loaded."""


def _read_regular_nofollow(path):
    """Read one frozen regular file without following its final component."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ContractError("frozen input must be a regular non-symlink")
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContractError("frozen input changed type")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("frozen input read failure") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _physical(path):
    return hashlib.sha256(_read_regular_nofollow(path)).hexdigest()


ROOT = Path(__file__).resolve().parent.parent
_R2_CLIENT_PATH = ROOT / "har1r2" / "preflight_client.py"
_R2_CLIENT_BYTES = _read_regular_nofollow(_R2_CLIENT_PATH)
if hashlib.sha256(_R2_CLIENT_BYTES).hexdigest() != R2_CLIENT_PHYSICAL_SHA256:
    raise ImportError("R2 safety utility physical hash mismatch")
R2_SAFETY = ModuleType("_har1r3_bound_r2_safety")
R2_SAFETY.__file__ = str(_R2_CLIENT_PATH)
exec(compile(_R2_CLIENT_BYTES, str(_R2_CLIENT_PATH), "exec"), R2_SAFETY.__dict__)

ContractError = R2_SAFETY.ContractError
_pairs = R2_SAFETY._pairs
_constant = R2_SAFETY._constant
_canonical = R2_SAFETY._canonical
_json_exact = R2_SAFETY._json_exact
canonical_sha256 = R2_SAFETY.canonical_sha256
_utc = R2_SAFETY._utc
_utc_now = R2_SAFETY._utc_now
_posix_deadline = R2_SAFETY._posix_deadline
_require_production_alarm_available = R2_SAFETY._require_production_alarm_available
reject_existing_target = R2_SAFETY.reject_existing_target

RUN_ID = "har1r3-tech-reachability-20260729-v1"
EVIDENCE_RELATIVE_PATH = "har1r3/technical_evidence.jsonl"
EVIDENCE_SCHEMA_VERSION = "har1r3-technical-evidence.v1"
PROXY = "http://127.0.0.1:7897"
PROBES = (
    (1, "GET", "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", 1048576),
    (2, "HEAD", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip", 0),
    (3, "GET", "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-07.zip.CHECKSUM", 512),
)
_PLAN_PROBES = (
    dict(sequence=1, method=PROBES[0][1], url=PROBES[0][2], body_cap_bytes=PROBES[0][3], success_contract="HTTP_200_AND_NONEMPTY_BODY"),
    dict(sequence=2, method=PROBES[1][1], url=PROBES[1][2], body_cap_bytes=PROBES[1][3], success_contract="HTTP_200_AND_ZERO_BODY"),
    dict(sequence=3, method=PROBES[2][1], url=PROBES[2][2], body_cap_bytes=PROBES[2][3], success_contract="HTTP_200_AND_EXACT_SHA256_BASENAME_PAIR"),
)
_CLOSED_R2_PLAN = {
    "run_id": "har1r2-source-preflight-20260729-v1",
    "activation_path": "config/sol_activation.har1-btcusdt-source-preflight-r2f.v1.json",
    "activation_raw_physical_sha256": R2_ACTIVATION_PHYSICAL_SHA256,
    "activation_canonical_sha256": R2_ACTIVATION_CANONICAL_SHA256,
    "evidence_path": "har1r2/evidence.jsonl",
    "evidence_physical_sha256": R2_EVIDENCE_PHYSICAL_SHA256,
    "evidence_bytes": 4304,
    "record_count": 2,
    "state": "SEALED_PROTOCOL_FAILURE",
    "terminal_sequence": 1,
    "terminal_method": "GET",
    "terminal_url": "https://www.binance.com/ja",
    "terminal_status_code": 202,
    "terminal_response_bytes": 0,
    "terminal_request_elapsed_ms": 1262,
    "terminal_outcome": "FAILURE",
    "terminal_error": "ContractError",
    "later_requests": 0,
    "zip_body_bytes": 0,
    "market_rows": 0,
}


def _probe_plan():
    return [{"sequence": sequence, "method": method, "url": url, "body_cap_bytes": cap} for sequence, method, url, cap in PROBES]


def load_strict_json(path):
    try:
        text = _read_regular_nofollow(path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError("frozen JSON invalid UTF-8") from exc
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def _validate_route(path):
    document = load_strict_json(path)
    if document.get("schema_version") != "sol-har1r3-dual-lane-successor-route.v1" or document.get("decision_id") != "SOL_HAR1R3_DUAL_LANE_SUCCESSOR_ROUTE.v1":
        raise ContractError("R3 route identity")
    return canonical_sha256(document, "decision_sha256", "msta-hed/sol-har1r3-dual-lane-successor-route/v1")


def validate_technical_plan(path):
    document = load_strict_json(path)
    fields = {"schema_version", "route_id", "route_physical_sha256", "route_canonical_sha256", "closed_r2", "run_id", "evidence_path", "proxy", "concurrency", "redirects", "retries", "cookies", "authentication", "per_probe_network_read_timeout_seconds", "total_network_read_budget_seconds", "probes", "execution_semantics", "prohibitions", "canonical_self_digest", "technical_plan_sha256"}
    if set(document) != fields:
        raise ContractError("technical plan schema")
    expected = {
        "schema_version": "har1r3-technical-plan.v1",
        "route_id": "SOL_HAR1R3_DUAL_LANE_SUCCESSOR_ROUTE.v1",
        "route_physical_sha256": R3_ROUTE_PHYSICAL_SHA256,
        "route_canonical_sha256": R3_ROUTE_CANONICAL_SHA256,
        "closed_r2": _CLOSED_R2_PLAN,
        "run_id": RUN_ID,
        "evidence_path": EVIDENCE_RELATIVE_PATH,
        "proxy": PROXY,
        "concurrency": 1,
        "redirects": 0,
        "retries": 0,
        "cookies": False,
        "authentication": False,
        "per_probe_network_read_timeout_seconds": 20,
        "total_network_read_budget_seconds": 60,
        "probes": list(_PLAN_PROBES),
        "execution_semantics": {
            "independent_probe_failure": "DURABLY_RECORD_THEN_CONTINUE_NEXT_DISTINCT_PROBE_NOT_A_RETRY",
            "evidence_durability_failure": "STOP_ALL_REMAINING_NETWORK_NO_AGGREGATE_UPGRADE",
            "budget_exhausted": "WRITE_ATTEMPTED_FALSE_FAILURE_FOR_EACH_REMAINING_PROBE",
            "aggregate_success": "ALL_THREE_PROBES_SUCCESS",
            "response_close": "BEFORE_PROBE_RECORD_WRITE",
            "terminal": "AGGREGATE_PROTOCOL_TERMINAL_NOT_WHOLE_FILE_SEAL",
            "seal": "ONLY_AFTER_CLOSE_SUCCESS_AND_STRICT_READ_ONLY_READBACK",
        },
        "prohibitions": {"zip_get": False, "zip_body": False, "market_row_read_or_parse": False, "network_without_future_activation": False},
        "canonical_self_digest": {"algorithm": "SHA-256_CANONICAL_JSON", "digest_field": "technical_plan_sha256", "domain_prefix_utf8": "msta-hed/har1r3-technical-plan/v1"},
    }
    for key, value in expected.items():
        if key not in document or not _json_exact(document[key], value):
            raise ContractError("technical plan field: " + key)
    return canonical_sha256(document, "technical_plan_sha256", "msta-hed/har1r3-technical-plan/v1")


def validate_terms_contract(path):
    document = load_strict_json(path)
    fields = {"schema_version", "route_id", "route_physical_sha256", "route_canonical_sha256", "closed_r2", "run_id", "session", "top_level_navigation_limit", "session_budget_seconds", "navigations", "redirect_policy", "interaction_boundary", "required_manifest_fields", "legal_conclusion", "maximum_claim", "canonical_self_digest", "terms_evidence_contract_sha256"}
    if set(document) != fields:
        raise ContractError("terms contract schema")
    expected = {
        "schema_version": "har1r3-terms-evidence-contract.v1",
        "route_id": "SOL_HAR1R3_DUAL_LANE_SUCCESSOR_ROUTE.v1",
        "route_physical_sha256": R3_ROUTE_PHYSICAL_SHA256,
        "route_canonical_sha256": R3_ROUTE_CANONICAL_SHA256,
        "closed_r2": {
            "activation_path": "config/sol_activation.har1-btcusdt-source-preflight-r2f.v1.json",
            "activation_raw_physical_sha256": R2_ACTIVATION_PHYSICAL_SHA256,
            "activation_canonical_sha256": R2_ACTIVATION_CANONICAL_SHA256,
            "evidence_path": "har1r2/evidence.jsonl",
            "evidence_physical_sha256": R2_EVIDENCE_PHYSICAL_SHA256,
            "evidence_bytes": 4304,
            "record_count": 2,
            "state": "SEALED_PROTOCOL_FAILURE",
            "terminal_fact": {"sequence": 1, "method": "GET", "url": "https://www.binance.com/ja", "status_code": 202, "response_bytes": 0, "request_elapsed_ms": 1262, "outcome": "FAILURE", "error": "ContractError"},
            "later_requests": 0,
            "zip_body_bytes": 0,
            "market_rows": 0,
            "causal_or_legal_inference": "NOT_ESTABLISHED",
        },
        "run_id": "har1r3-terms-evidence-20260729-v1",
        "session": "NEW_ISOLATED_UNAUTHENTICATED_NO_EXISTING_COOKIE",
        "top_level_navigation_limit": 2,
        "session_budget_seconds": 240,
        "navigations": [{"sequence": 1, "url": "https://www.binance.com/ja/terms"}, {"sequence": 2, "url": "https://github.com/binance/binance-public-data"}],
        "redirect_policy": {"same_origin": "RECORD_AND_ALLOW", "cross_origin_login_wall_or_empty_page": "RECORD_UNRESOLVED_AND_STOP_NAVIGATION"},
        "interaction_boundary": {"login_form_submit": False, "accept_button": False, "account_access": False, "download": False, "subresources_as_authority_evidence": False},
        "required_manifest_fields": ["requested_url", "final_url", "captured_at_utc", "page_title", "visible_version_or_effective_date", "bounded_visible_excerpt", "visible_license_or_terms_links_not_opened", "screenshot_path", "screenshot_sha256", "status", "limitations"],
        "legal_conclusion": False,
        "maximum_claim": "VISIBLE_PAGE_AND_PROVENANCE_EVIDENCE_PENDING_HUMAN_AND_SOL_REVIEW",
        "canonical_self_digest": {"algorithm": "SHA-256_CANONICAL_JSON", "digest_field": "terms_evidence_contract_sha256", "domain_prefix_utf8": "msta-hed/har1r3-terms-evidence-contract/v1"},
    }
    for key, value in expected.items():
        if key not in document or not _json_exact(document[key], value):
            raise ContractError("terms contract field: " + key)
    return canonical_sha256(document, "terms_evidence_contract_sha256", "msta-hed/har1r3-terms-evidence-contract/v1")


def _validate_r2_activation(path):
    document = load_strict_json(path)
    if document.get("decision_id") != "SOL_HAR1R2_SOURCE_PREFLIGHT_ACTIVATION.v1":
        raise ContractError("closed R2 activation identity")
    actual = canonical_sha256(document, "activation_sha256", "msta-hed/har1r2-activation/v1")
    if actual != R2_ACTIVATION_CANONICAL_SHA256:
        raise ContractError("closed R2 activation canonical hash")
    return actual


def _parse_jsonl(raw):
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise ContractError("strict JSONL framing")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise ContractError("empty JSONL record")
    records = []
    for line in lines:
        try:
            records.append(json.loads(line.decode("utf-8", errors="strict"), object_pairs_hook=_pairs, parse_constant=_constant))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ContractError) as exc:
            raise ContractError("strict JSONL record") from exc
    if any(not isinstance(record, dict) for record in records):
        raise ContractError("JSONL object required")
    return lines, records


def validate_closed_r2_artifacts(root=ROOT):
    activation_path = Path(root) / "config" / "sol_activation.har1-btcusdt-source-preflight-r2f.v1.json"
    evidence_path = Path(root) / "har1r2" / "evidence.jsonl"
    if _physical(activation_path) != R2_ACTIVATION_PHYSICAL_SHA256 or _validate_r2_activation(activation_path) != R2_ACTIVATION_CANONICAL_SHA256:
        raise ContractError("closed R2 activation drift")
    raw = _read_regular_nofollow(evidence_path)
    if hashlib.sha256(raw).hexdigest() != R2_EVIDENCE_PHYSICAL_SHA256 or len(raw) != 4304:
        raise ContractError("closed R2 evidence physical drift")
    lines, records = _parse_jsonl(raw)
    if len(records) != 2:
        raise ContractError("closed R2 evidence record count")
    previous = "0" * 64
    for line, record in zip(lines, records):
        if record.get("previous_sha256") != previous:
            raise ContractError("closed R2 evidence chain")
        previous = hashlib.sha256(line + b"\n").hexdigest()
    first, terminal = records
    if first.get("record_type") != "ACTIVATION" or first.get("activation_raw_physical_sha256") != R2_ACTIVATION_PHYSICAL_SHA256 or first.get("activation_sha256") != R2_ACTIVATION_CANONICAL_SHA256:
        raise ContractError("closed R2 evidence activation")
    terminal_expected = {"record_type": "TERMINAL", "terminal": True, "sequence": 1, "method": "GET", "url": "https://www.binance.com/ja", "status_code": 202, "response_bytes": 0, "outcome": "FAILURE", "error": "ContractError"}
    for key, value in terminal_expected.items():
        if key not in terminal or not _json_exact(terminal[key], value):
            raise ContractError("closed R2 terminal fact: " + key)
    return True


class EvidenceDurabilityError(RuntimeError):
    external_evidence_state = "UNSEALED_OR_PARTIAL"


class EvidenceCloseFailureAfterFsyncError(EvidenceDurabilityError):
    external_evidence_state = "REVIEW_REQUIRED_CLOSE_ERROR"

    def __init__(self):
        super().__init__("EVIDENCE_CLOSE_FAILURE_AFTER_FSYNC")


class EvidenceReadbackValidationError(RuntimeError):
    external_evidence_state = "UNSEALED_OR_REVIEW_REQUIRED"


_ACTIVATION_FIELDS = {"decision_id", "permission", "issued_at_utc", "expires_at_utc", "bindings", "canonical_self_digest", "activation_sha256"}
_BINDING_FIELDS = {"r3_route_physical", "r3_route_canonical", "r2_activation_physical", "r2_activation_canonical", "r2_evidence_physical", "technical_plan_physical", "technical_plan_canonical", "terms_contract_physical", "terms_contract_canonical", "r2_client_physical", "client_physical", "test_physical", "run_id", "evidence_path", "probes"}


def _parse_raw_activation(raw):
    if type(raw) is not bytes:
        raise ContractError("activation input must be raw bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ContractError("activation UTF-8 BOM denied")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ContractError) as exc:
        raise ContractError("activation invalid strict JSON") from exc
    if not isinstance(document, dict):
        raise ContractError("activation object required")
    return document, hashlib.sha256(raw).hexdigest()


def _hex_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _capability_factory():
    token = object()
    registry, activations, lock = {}, set(), threading.Lock()

    class TechnicalCapability:
        __slots__ = ("_lock", "_used", "_bindings", "_issued", "_expires", "_pid", "_activation_sha256", "_activation_raw_physical_sha256", "_decision_id", "_permission")

        def __init__(self, supplied, bindings, issued, expires, canonical, physical, decision_id, permission):
            if supplied is not token:
                raise PermissionError("R3 issuer required")
            self._lock, self._used = threading.Lock(), False
            self._bindings = MappingProxyType(json.loads(_canonical(bindings).decode("utf-8")))
            self._issued, self._expires, self._pid = issued, expires, os.getpid()
            self._activation_sha256, self._activation_raw_physical_sha256 = canonical, physical
            self._decision_id, self._permission = decision_id, permission

        def __copy__(self):
            raise PermissionError("opaque R3 capability")

        def __deepcopy__(self, _memo):
            raise PermissionError("opaque R3 capability")

        def __reduce__(self):
            raise PermissionError("opaque R3 capability")

    def issue(raw_activation, now=None):
        document, raw_physical = _parse_raw_activation(raw_activation)
        if set(document) != _ACTIVATION_FIELDS:
            raise ContractError("activation schema")
        if document.get("decision_id") != "SOL_HAR1R3_TECH_REACHABILITY_ACTIVATION.v1" or document.get("permission") != "ONE_THREE_PROBE_DIAGNOSTIC_BATCH":
            raise ContractError("activation permission")
        if document.get("canonical_self_digest") != {"algorithm": "SHA-256_CANONICAL_JSON", "digest_field": "activation_sha256", "domain_prefix_utf8": "msta-hed/har1r3-technical-activation/v1"}:
            raise ContractError("activation self digest metadata")
        activation = canonical_sha256(document, "activation_sha256", "msta-hed/har1r3-technical-activation/v1")
        issued, expires = _utc(document["issued_at_utc"]), _utc(document["expires_at_utc"])
        current = time.time() if now is None else now
        if not 0 < expires - issued <= 900:
            raise ContractError("activation TTL")
        if not isinstance(current, (int, float)) or isinstance(current, bool) or not issued <= current <= expires:
            raise ContractError("activation time window")
        bindings = document.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
            raise ContractError("activation bindings")
        expected = {
            "r3_route_physical": R3_ROUTE_PHYSICAL_SHA256,
            "r3_route_canonical": R3_ROUTE_CANONICAL_SHA256,
            "r2_activation_physical": R2_ACTIVATION_PHYSICAL_SHA256,
            "r2_activation_canonical": R2_ACTIVATION_CANONICAL_SHA256,
            "r2_evidence_physical": R2_EVIDENCE_PHYSICAL_SHA256,
            "technical_plan_physical": TECHNICAL_PLAN_PHYSICAL_SHA256,
            "technical_plan_canonical": TECHNICAL_PLAN_CANONICAL_SHA256,
            "terms_contract_physical": TERMS_CONTRACT_PHYSICAL_SHA256,
            "terms_contract_canonical": TERMS_CONTRACT_CANONICAL_SHA256,
            "r2_client_physical": R2_CLIENT_PHYSICAL_SHA256,
            "run_id": RUN_ID,
            "evidence_path": EVIDENCE_RELATIVE_PATH,
            "probes": _probe_plan(),
        }
        for key, value in expected.items():
            if key not in bindings or not _json_exact(bindings[key], value):
                raise ContractError("activation binding: " + key)
        if not _hex_digest(bindings.get("client_physical")) or not _hex_digest(bindings.get("test_physical")):
            raise ContractError("activation final file hash")
        with lock:
            if activation in activations:
                raise PermissionError("activation already issued")
            capability = TechnicalCapability(token, bindings, issued, expires, activation, raw_physical, document["decision_id"], document["permission"])
            activations.add(activation)
            registry[id(capability)] = capability
        return capability

    def consume(capability, now):
        if type(capability) is not TechnicalCapability or capability._pid != os.getpid():
            raise PermissionError("foreign R3 capability")
        with lock:
            if registry.get(id(capability)) is not capability:
                raise PermissionError("unissued R3 capability")
        with capability._lock:
            if capability._used or not capability._issued <= now <= capability._expires:
                raise PermissionError("R3 capability reused, premature, or expired")
            capability._used = True

    return TechnicalCapability, issue, consume


_TechnicalCapability, issue_activation_capability, _consume_capability = _capability_factory()


def require_future_sol_r3_activation(*_args, **_kwargs):
    raise PermissionError("WAIT_SOL_R3_TECHNICAL_ACTIVATION")


def _pre_tcp_recheck(capability):
    bindings = capability._bindings
    if not _json_exact(bindings.get("probes"), _probe_plan()):
        raise ContractError("frozen R3 probes drift")
    physical = (
        (ROOT / "config" / "sol_decision.har1r3-dual-lane-successor-route.v1.json", "r3_route_physical", R3_ROUTE_PHYSICAL_SHA256),
        (ROOT / "config" / "sol_activation.har1-btcusdt-source-preflight-r2f.v1.json", "r2_activation_physical", R2_ACTIVATION_PHYSICAL_SHA256),
        (ROOT / "har1r2" / "evidence.jsonl", "r2_evidence_physical", R2_EVIDENCE_PHYSICAL_SHA256),
        (ROOT / "har1r3" / "technical_plan.json", "technical_plan_physical", TECHNICAL_PLAN_PHYSICAL_SHA256),
        (ROOT / "har1r3" / "terms_evidence_contract.json", "terms_contract_physical", TERMS_CONTRACT_PHYSICAL_SHA256),
        (_R2_CLIENT_PATH, "r2_client_physical", R2_CLIENT_PHYSICAL_SHA256),
        (Path(__file__), "client_physical", bindings["client_physical"]),
        (Path(__file__).with_name("test_technical_client.py"), "test_physical", bindings["test_physical"]),
    )
    for path, name, expected in physical:
        if _physical(path) != expected or bindings[name] != expected:
            raise ContractError("physical drift: " + name)
    canonical = (
        (_validate_route(ROOT / "config" / "sol_decision.har1r3-dual-lane-successor-route.v1.json"), "r3_route_canonical", R3_ROUTE_CANONICAL_SHA256),
        (_validate_r2_activation(ROOT / "config" / "sol_activation.har1-btcusdt-source-preflight-r2f.v1.json"), "r2_activation_canonical", R2_ACTIVATION_CANONICAL_SHA256),
        (validate_technical_plan(ROOT / "har1r3" / "technical_plan.json"), "technical_plan_canonical", TECHNICAL_PLAN_CANONICAL_SHA256),
        (validate_terms_contract(ROOT / "har1r3" / "terms_evidence_contract.json"), "terms_contract_canonical", TERMS_CONTRACT_CANONICAL_SHA256),
    )
    for actual, name, expected in canonical:
        if actual != expected or bindings[name] != expected:
            raise ContractError("canonical drift: " + name)
    validate_closed_r2_artifacts()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class _ForcedHttpsProxyHandler(urllib.request.ProxyHandler):
    def __init__(self):
        super().__init__({"https": PROXY})

    def proxy_open(self, request, proxy, protocol):
        if proxy != PROXY or protocol != "https":
            raise ContractError("fixed R3 HTTPS proxy required")
        request.set_proxy("127.0.0.1:7897", "https")
        return None


def _build_production_opener():
    return urllib.request.build_opener(_ForcedHttpsProxyHandler(), _NoRedirect())


_PRODUCTION_HEADERS = {"Accept-Encoding": "identity", "Connection": "close", "User-Agent": "agent-trade-emotion-har1r3-technical/1.0"}


def _production_request(method, url):
    return urllib.request.Request(url, method=method, headers=_PRODUCTION_HEADERS)


def _headers(response):
    source = getattr(response, "headers", {}) or {}
    names = ("Content-Length", "Content-Type", "Last-Modified", "ETag", "Strict-Transport-Security", "X-Content-Type-Options")
    return {name: source.get(name) for name in names if source.get(name) is not None}


def _response_status(response):
    return getattr(response, "status", getattr(response, "code", None))


def _close_response(response):
    close = getattr(response, "close", None)
    if close is not None:
        close()


def _activation_record(capability, recorded_at):
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "record_type": "ACTIVATION",
        "terminal": False,
        "activation_sha256": capability._activation_sha256,
        "activation_raw_physical_sha256": capability._activation_raw_physical_sha256,
        "decision_id": capability._decision_id,
        "permission": capability._permission,
        "issued_at_utc": _utc_now(capability._issued),
        "expires_at_utc": _utc_now(capability._expires),
        "bindings": dict(capability._bindings),
        "run_id": RUN_ID,
        "proxy": PROXY,
        "request_headers": dict(_PRODUCTION_HEADERS),
        "probes": _probe_plan(),
        "recorded_at_utc": _utc_now(recorded_at),
    }


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
                raise ContractError("nonregular R3 evidence target")
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
                    raise OSError("short R3 evidence write")
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


def _validate_probe_success(sequence, status, body):
    if not _json_exact(status, 200):
        raise ContractError("unexpected HTTP status")
    if type(body) is not bytes:
        raise ContractError("response body type")
    cap = PROBES[sequence - 1][3]
    if len(body) > cap:
        raise ContractError("body cap")
    if sequence == 1 and not body:
        raise ContractError("README body empty")
    if sequence == 2 and body:
        raise ContractError("HEAD body nonzero")
    if sequence == 3:
        parts = body.strip().split()
        if len(parts) != 2 or len(parts[0]) != 64 or any(byte not in b"0123456789abcdefABCDEF" for byte in parts[0]) or parts[1] != b"BTCUSDT-1m-2025-07.zip":
            raise ContractError("checksum exact contract")


def _run_with_transport(capability, transport, writer, clock, wall_clock=None, deadline_factory=None):
    del capability
    wall_clock = time.time if wall_clock is None else wall_clock
    network_elapsed, probe_records = 0.0, []
    for sequence, method, url, body_cap in PROBES:
        attempted, status, body, response_headers = False, None, None, {}
        started_at, probe_clock = wall_clock(), clock()
        error_name = None
        if network_elapsed >= 60:
            error_name = "TOTAL_BUDGET_EXHAUSTED"
            elapsed = 0.0
        else:
            timeout = min(20, 60 - network_elapsed)
            response = None
            try:
                def execute():
                    nonlocal attempted, status, body, response, response_headers
                    attempted = True
                    try:
                        response = transport(method, url, timeout)
                    except urllib.error.HTTPError as exc:
                        response = exc
                    status = _response_status(response)
                    response_headers = _headers(response)
                    try:
                        body = response.read(body_cap + 1)
                    finally:
                        closing, response = response, None
                        _close_response(closing)
                if deadline_factory is None:
                    execute()
                else:
                    with deadline_factory(timeout):
                        execute()
                _validate_probe_success(sequence, status, body)
            except Exception as exc:
                error_name = type(exc).__name__
                if response is not None:
                    closing, response = response, None
                    try:
                        _close_response(closing)
                    except Exception:
                        pass
            elapsed = max(0.0, clock() - probe_clock)
            network_elapsed += elapsed
            if attempted and elapsed >= timeout and error_name is None:
                error_name = "PROBE_DEADLINE_EXCEEDED_AFTER_RETURN"
            elif network_elapsed >= 60 and error_name is None:
                error_name = "TOTAL_BUDGET_EXHAUSTED_AFTER_PROBE"
        outcome = "SUCCESS" if error_name is None else "FAILURE"
        record = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "record_type": "PROBE",
            "terminal": False,
            "sequence": sequence,
            "method": method,
            "url": url,
            "request_attempted": attempted,
            "outcome": outcome,
            "request_started_at_utc": _utc_now(started_at),
            "response_completed_at_utc": _utc_now(wall_clock()),
            "request_elapsed_ms": int(elapsed * 1000),
            "cumulative_elapsed_ms": int(network_elapsed * 1000),
            "concurrency": 1,
        }
        if status is not None:
            record["status_code"] = status
        if body is not None:
            record["response_bytes"] = len(body)
            record["body_sha256"] = hashlib.sha256(body).hexdigest()
            record["body_base64"] = base64.b64encode(body).decode("ascii")
        if response_headers:
            record["response_headers"] = response_headers
        if sequence == 3 and outcome == "SUCCESS":
            parts = body.strip().split()
            record["checksum_sha256"] = parts[0].decode("ascii").lower()
            record["checksum_basename"] = parts[1].decode("ascii")
        if error_name is not None:
            record["error"] = error_name
        _durable_write(writer, record)
        probe_records.append(record)
    success = all(record["outcome"] == "SUCCESS" for record in probe_records)
    aggregate = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "record_type": "AGGREGATE_TERMINAL",
        "terminal": True,
        "outcome": "SUCCESS" if success else "FAILURE",
        "probe_results": [{"sequence": record["sequence"], "outcome": record["outcome"], "request_attempted": record["request_attempted"]} for record in probe_records],
        "successful_probes": sum(record["outcome"] == "SUCCESS" for record in probe_records),
        "failed_probes": sum(record["outcome"] == "FAILURE" for record in probe_records),
        "cumulative_elapsed_ms": int(network_elapsed * 1000),
        "recorded_at_utc": _utc_now(wall_clock()),
    }
    _durable_write(writer, aggregate)
    return success


def _strict_body_from_record(record, body_cap, outcome):
    body_fields = {"response_bytes", "body_sha256", "body_base64"}
    present = body_fields.intersection(record)
    if present and present != body_fields:
        raise EvidenceReadbackValidationError("R3 incomplete body evidence")
    if not present:
        if outcome == "SUCCESS":
            raise EvidenceReadbackValidationError("R3 success body evidence missing")
        return None
    encoded = record["body_base64"]
    if type(encoded) is not str:
        raise EvidenceReadbackValidationError("R3 body base64 type")
    try:
        body = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise EvidenceReadbackValidationError("R3 body base64") from exc
    if base64.b64encode(body).decode("ascii") != encoded:
        raise EvidenceReadbackValidationError("R3 body base64 canonical")
    if type(record["response_bytes"]) is not int or record["response_bytes"] != len(body):
        raise EvidenceReadbackValidationError("R3 response byte count")
    if not _hex_digest(record["body_sha256"]) or record["body_sha256"] != hashlib.sha256(body).hexdigest():
        raise EvidenceReadbackValidationError("R3 body hash")
    maximum = body_cap if outcome == "SUCCESS" else body_cap + 1
    if len(body) > maximum:
        raise EvidenceReadbackValidationError("R3 read cap evidence")
    return body


def _validate_probe_readback(record, expected, previous_cumulative):
    sequence, method, url, body_cap = expected
    base_fields = {
        "schema_version", "record_type", "terminal", "sequence", "method", "url",
        "request_attempted", "outcome", "request_started_at_utc",
        "response_completed_at_utc", "request_elapsed_ms",
        "cumulative_elapsed_ms", "concurrency", "previous_sha256",
    }
    if not base_fields.issubset(record):
        raise EvidenceReadbackValidationError("R3 probe fields missing")
    if record["schema_version"] != EVIDENCE_SCHEMA_VERSION or record["record_type"] != "PROBE" or record["terminal"] is not False:
        raise EvidenceReadbackValidationError("R3 probe identity")
    if not _json_exact(record["sequence"], sequence) or record["method"] != method or record["url"] != url:
        raise EvidenceReadbackValidationError("R3 frozen probe drift")
    if type(record["request_attempted"]) is not bool or record["outcome"] not in {"SUCCESS", "FAILURE"}:
        raise EvidenceReadbackValidationError("R3 probe outcome type")
    for name in ("request_elapsed_ms", "cumulative_elapsed_ms"):
        if type(record[name]) is not int or record[name] < 0:
            raise EvidenceReadbackValidationError("R3 elapsed type")
    if not _json_exact(record["concurrency"], 1):
        raise EvidenceReadbackValidationError("R3 concurrency")
    try:
        started = _utc(record["request_started_at_utc"])
        completed = _utc(record["response_completed_at_utc"])
    except ContractError as exc:
        raise EvidenceReadbackValidationError("R3 probe timestamp") from exc
    if started > completed:
        raise EvidenceReadbackValidationError("R3 probe timestamp order")
    delta = record["cumulative_elapsed_ms"] - previous_cumulative
    if delta not in {record["request_elapsed_ms"], record["request_elapsed_ms"] + 1}:
        raise EvidenceReadbackValidationError("R3 cumulative elapsed")
    outcome, attempted = record["outcome"], record["request_attempted"]
    if record["cumulative_elapsed_ms"] > 60000:
        raise EvidenceReadbackValidationError("R3 total budget exceeded")
    if attempted and previous_cumulative >= 60000:
        raise EvidenceReadbackValidationError("R3 attempted after total budget")
    if not attempted and previous_cumulative < 60000:
        raise EvidenceReadbackValidationError("R3 unattempted before total budget")
    if attempted and outcome == "FAILURE":
        maximum_failure_elapsed = min(20000, 60000 - previous_cumulative)
        if record["request_elapsed_ms"] > maximum_failure_elapsed:
            raise EvidenceReadbackValidationError("R3 attempted failure deadline")
    body = _strict_body_from_record(record, body_cap, outcome)
    if "status_code" in record and (type(record["status_code"]) is not int or not 100 <= record["status_code"] <= 599):
        raise EvidenceReadbackValidationError("R3 status type")
    if "response_headers" in record:
        headers = record["response_headers"]
        allowed_headers = {"Content-Length", "Content-Type", "Last-Modified", "ETag", "Strict-Transport-Security", "X-Content-Type-Options"}
        if type(headers) is not dict or not set(headers).issubset(allowed_headers) or any(type(value) is not str for value in headers.values()):
            raise EvidenceReadbackValidationError("R3 response headers")
    conditional = set()
    if "status_code" in record:
        conditional.add("status_code")
    if body is not None:
        conditional.update({"response_bytes", "body_sha256", "body_base64"})
    if "response_headers" in record:
        conditional.add("response_headers")
    if outcome == "SUCCESS":
        conditional.update({"status_code", "response_bytes", "body_sha256", "body_base64"})
        if "status_code" not in record or body is None or "error" in record or not attempted:
            raise EvidenceReadbackValidationError("R3 contradictory success")
        try:
            _validate_probe_success(sequence, record["status_code"], body)
        except ContractError as exc:
            raise EvidenceReadbackValidationError("R3 success contract") from exc
        if record["request_elapsed_ms"] >= 20000 or record["cumulative_elapsed_ms"] >= 60000:
            raise EvidenceReadbackValidationError("R3 success deadline")
        if sequence == 3:
            conditional.update({"checksum_sha256", "checksum_basename"})
            parts = body.strip().split()
            if record.get("checksum_sha256") != parts[0].decode("ascii").lower() or record.get("checksum_basename") != parts[1].decode("ascii"):
                raise EvidenceReadbackValidationError("R3 checksum derivation")
        elif "checksum_sha256" in record or "checksum_basename" in record:
            raise EvidenceReadbackValidationError("R3 unexpected checksum evidence")
    else:
        conditional.add("error")
        if type(record.get("error")) is not str or not record["error"]:
            raise EvidenceReadbackValidationError("R3 failure error missing")
        if "checksum_sha256" in record or "checksum_basename" in record:
            raise EvidenceReadbackValidationError("R3 checksum on failure")
        if not attempted:
            if record["error"] != "TOTAL_BUDGET_EXHAUSTED" or record["request_elapsed_ms"] != 0 or record["cumulative_elapsed_ms"] != previous_cumulative:
                raise EvidenceReadbackValidationError("R3 unattempted failure")
            if any(name in record for name in ("status_code", "response_bytes", "body_sha256", "body_base64", "response_headers")):
                raise EvidenceReadbackValidationError("R3 unattempted response evidence")
    if set(record) != base_fields | conditional:
        raise EvidenceReadbackValidationError("R3 unexpected probe fields")
    return record["cumulative_elapsed_ms"]


def _readback_records(raw, capability):
    try:
        lines, records = _parse_jsonl(raw)
    except ContractError as exc:
        raise EvidenceReadbackValidationError("strict R3 JSONL") from exc
    if len(records) != 5:
        raise EvidenceReadbackValidationError("exact R3 record count")
    activation = records[0]
    activation_fields = {
        "schema_version", "record_type", "terminal", "activation_sha256",
        "activation_raw_physical_sha256", "decision_id", "permission",
        "issued_at_utc", "expires_at_utc", "bindings", "run_id", "proxy",
        "request_headers", "probes", "recorded_at_utc", "previous_sha256",
    }
    if set(activation) != activation_fields or activation["record_type"] != "ACTIVATION" or activation["terminal"] is not False:
        raise EvidenceReadbackValidationError("R3 activation exact schema")
    scalar = (activation["schema_version"], activation["activation_sha256"], activation["activation_raw_physical_sha256"], activation["decision_id"], activation["permission"], activation["run_id"], activation["proxy"])
    expected_scalar = (EVIDENCE_SCHEMA_VERSION, capability._activation_sha256, capability._activation_raw_physical_sha256, capability._decision_id, capability._permission, RUN_ID, PROXY)
    if scalar != expected_scalar or not _json_exact(activation["bindings"], dict(capability._bindings)) or not _json_exact(activation["probes"], _probe_plan()) or not _json_exact(activation["request_headers"], _PRODUCTION_HEADERS):
        raise EvidenceReadbackValidationError("R3 activation binding drift")
    if activation["issued_at_utc"] != _utc_now(capability._issued) or activation["expires_at_utc"] != _utc_now(capability._expires):
        raise EvidenceReadbackValidationError("R3 activation time binding")
    try:
        recorded_at = _utc(activation["recorded_at_utc"])
    except ContractError as exc:
        raise EvidenceReadbackValidationError("R3 activation timestamp") from exc
    if not capability._issued <= recorded_at <= capability._expires:
        raise EvidenceReadbackValidationError("R3 activation timestamp window")
    if sum(record.get("record_type") == "ACTIVATION" for record in records) != 1:
        raise EvidenceReadbackValidationError("R3 activation unique")
    previous = "0" * 64
    for line, record in zip(lines, records):
        if record.get("previous_sha256") != previous:
            raise EvidenceReadbackValidationError("R3 raw-line chain")
        previous = hashlib.sha256(line + b"\n").hexdigest()
    probes, cumulative = records[1:4], 0
    for expected, record in zip(PROBES, probes):
        cumulative = _validate_probe_readback(record, expected, cumulative)
    aggregate = records[4]
    aggregate_fields = {
        "schema_version", "record_type", "terminal", "outcome",
        "probe_results", "successful_probes", "failed_probes",
        "cumulative_elapsed_ms", "recorded_at_utc", "previous_sha256",
    }
    expected_results = [{"sequence": record["sequence"], "outcome": record["outcome"], "request_attempted": record["request_attempted"]} for record in probes]
    successful = sum(record["outcome"] == "SUCCESS" for record in probes)
    failed = len(probes) - successful
    if set(aggregate) != aggregate_fields or aggregate["schema_version"] != EVIDENCE_SCHEMA_VERSION or aggregate["record_type"] != "AGGREGATE_TERMINAL" or aggregate["terminal"] is not True:
        raise EvidenceReadbackValidationError("R3 aggregate exact schema")
    if aggregate["outcome"] != ("SUCCESS" if successful == 3 else "FAILURE") or not _json_exact(aggregate["probe_results"], expected_results):
        raise EvidenceReadbackValidationError("R3 aggregate outcome")
    if not _json_exact(aggregate["successful_probes"], successful) or not _json_exact(aggregate["failed_probes"], failed) or not _json_exact(aggregate["cumulative_elapsed_ms"], cumulative):
        raise EvidenceReadbackValidationError("R3 aggregate derivation")
    try:
        aggregate_time = _utc(aggregate["recorded_at_utc"])
        last_probe_time = _utc(probes[-1]["response_completed_at_utc"])
    except ContractError as exc:
        raise EvidenceReadbackValidationError("R3 aggregate timestamp") from exc
    if aggregate_time < last_probe_time or sum(record.get("terminal") is True for record in records) != 1:
        raise EvidenceReadbackValidationError("R3 terminal unique last")
    return aggregate["outcome"]


def _readback_sealed_evidence(path, capability, protocol_success=None):
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise EvidenceReadbackValidationError("nonregular R3 readback")
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceReadbackValidationError("nonregular R3 readback")
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
        raise EvidenceReadbackValidationError("R3 readback open/read") from exc
    outcome = _readback_records(b"".join(chunks), capability)
    if protocol_success is not None and protocol_success is not (outcome == "SUCCESS"):
        raise EvidenceReadbackValidationError("R3 protocol outcome mismatch")
    return {"external_evidence_state": "SEALED", "protocol_outcome": outcome, "aggregate_terminal_reliable": True}


def run_technical_preflight(capability):
    """The sole production transport entry point; no transport injection."""
    _consume_capability(capability, time.time())
    _pre_tcp_recheck(capability)
    _require_production_alarm_available()
    opener = _build_production_opener()
    writer = _EvidenceWriter(Path(__file__).with_name("technical_evidence.jsonl"))
    writer.prepare()
    try:
        _durable_write(writer, _activation_record(capability, time.time()))
        success = _run_with_transport(capability, lambda method, url, timeout: opener.open(_production_request(method, url), timeout=timeout), writer, time.monotonic, time.time, _posix_deadline)
    except BaseException:
        try:
            _durable_close(writer)
        except EvidenceCloseFailureAfterFsyncError:
            pass
        raise
    else:
        _durable_close(writer)
        return _readback_sealed_evidence(writer.path, capability, success)
