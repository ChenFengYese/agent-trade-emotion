"""Dormant HAR1R4 source/terms raw-evidence client.

Import performs no network or output creation.  The only production entry is
``execute_source_terms_raw(capability)``; it accepts no transport injection.
"""
import base64
import copy
import datetime as dt
import errno
import hashlib
import json
import os
import re
import socket
import stat
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType, ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "har1r4-source-terms-raw-20260729-v1"
PROXY = "http://127.0.0.1:7897"
ROUTE_PATH = "config/sol_decision.har1r4-source-terms-raw-route.v1.json"
PLAN_PATH = "har1r4/source_terms_request_plan.json"
CONTRACT_PATH = "har1r4/source_terms_contract.json"
ACTIVATION_PATH = "config/sol_activation.har1r4-source-terms-raw.v1.json"
EVIDENCE_PATH = "har1r4/evidence/requests.jsonl"
MANIFEST_PATH = "har1r4/evidence/manifest.json"
RAW_PATHS = (
    "har1r4/evidence/raw/github-repository-metadata.json",
    "har1r4/evidence/raw/github-master-commit.json",
    "har1r4/evidence/raw/github-master-tree.json",
    "har1r4/evidence/raw/binance-ja-terms.raw",
)

ROUTE_PHYSICAL_SHA256 = "1821db735137efd443b1ffd36f2726a9313e447d831d4d36ab7c102a994c15dd"
ROUTE_CANONICAL_SHA256 = "df0f06c41da124d84974f4ca911c889290598f17573f716000fcec2647a4f511"
PLAN_PHYSICAL_SHA256 = "f90a8fd86146489f35c5a1a98ddcfb10f5a17093bb60793957516b38e2b53159"
PLAN_CANONICAL_SHA256 = "94e57785aee738961a46260a3612e3c203938ed00ae075013393edafb9fc99af"
CONTRACT_PHYSICAL_SHA256 = "87c9a683c82f0d51cf54012071c2f9546dd12ead4015205798872c5f3d897bc1"
CONTRACT_CANONICAL_SHA256 = "a79a1c84f7d4d3298c3e338a4d784163b738cbb3cd541ebe53ecad5e5fc78a65"

R3_ROUTE_PHYSICAL = "6b23ca9248233929023b29c606466af7063929e23fe70e89d01e0f1b2fca8c8d"
R3_ROUTE_CANONICAL = "a21411873c7a793dc9d51983c4717ac3afad422bfe0d4f744679e9a51673b604"
R3_TECH_ACTIVATION_PHYSICAL = "e0c260b7cc01c0f3e837c7ed67bbc39d0286606a5fae2b391bb129e4c626ed5f"
R3_TECH_ACTIVATION_CANONICAL = "71f85475cb6c2ec99da27b5f22f3dbb152e93506e3ca6d76d84059ad97fb893e"
R3_TECH_EVIDENCE_PHYSICAL = "37ee748b04a412df58815da7421e51193878d3deb3ba3b8d02b0f6544d1c944f"
R3_TECH_CLIENT_PHYSICAL = "8a79d8c7f6a46c40d7e0fe5c016579e732209e013c9ad95f7165a4f11a50b73b"
R3_TERMS_ACTIVATION_PHYSICAL = "7aff484e8d3138fe6af0c56cae849b8f8fa4eca82711edcaf76ec61dee0ebe14"
R3_TERMS_ACTIVATION_CANONICAL = "f0051d8797572dfff835c3e2506ede3907d3d2342a4a40bd53f9babf4d2cc729"
R3_TERMS_CONTRACT_PHYSICAL = "0809b031cc722b3f3e1fab54f4f88a29c1a53609872270fb476c65f1ff7cec02"
R3_TERMS_CONTRACT_CANONICAL = "71a8592d35f01c4667a0eaff555cfb43dd5e2b6c245f206f3ca76c0a2fd082af"
R3_TERMS_MANIFEST_PHYSICAL = "43416222cd7188d7012740836ef2ac6d3029d19b461ea873abc4391f7546e0c2"
R3_TERMS_MANIFEST_CANONICAL = "607fce0bb36f05151e5eccb804ec7d9f4194c3929c801fc8b679138e467aeb38"
SEALED_README_BYTES = 5144
SEALED_README_SHA256 = "085ab91377aa9325d44f4c7ad27cce4ab381e158403e1d7df2bad39d1a66f7c6"
SEALED_README_GIT_BLOB_SHA1 = "311354cd82a76bcaaec588e6818e6c12644abef0"

GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Accept-Encoding": "identity",
    "Connection": "close",
    "User-Agent": "agent-trade-emotion-har1r4-source-terms/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}
TERMS_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Encoding": "identity",
    "Accept-Language": "ja",
    "Connection": "close",
    "User-Agent": "agent-trade-emotion-har1r4-source-terms/1.0",
}
REQUESTS = (
    (1, "GET", "https://api.github.com/repos/binance/binance-public-data", RAW_PATHS[0], 262144, "application/json", GITHUB_HEADERS),
    (2, "GET", "https://api.github.com/repos/binance/binance-public-data/commits/master", RAW_PATHS[1], 524288, "application/json", GITHUB_HEADERS),
    (3, "GET", "https://api.github.com/repos/binance/binance-public-data/git/trees/master", RAW_PATHS[2], 1048576, "application/json", GITHUB_HEADERS),
    (4, "GET", "https://www.binance.com/ja/terms", RAW_PATHS[3], 4194304, "text/html", TERMS_HEADERS),
)


class ContractError(ValueError):
    pass


class ProtocolViolation(RuntimeError):
    pass


class EvidenceDurabilityError(RuntimeError):
    pass


class EvidenceReadbackError(RuntimeError):
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


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_exact(left, right) for left, right in zip(actual, expected))
    return actual == expected


def _strict_json(raw):
    if type(raw) is not bytes or raw.startswith(b"\xef\xbb\xbf"):
        raise ContractError("strict raw UTF-8 JSON bytes required")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ContractError) as exc:
        raise ContractError("strict JSON") from exc
    if type(value) is not dict:
        raise ContractError("JSON object required")
    return value


def _canonical_digest(document, field, domain):
    if field not in document or type(document[field]) is not str:
        raise ContractError("canonical digest field")
    unsigned = dict(document)
    claimed = unsigned.pop(field)
    actual = hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical(unsigned)).hexdigest()
    if claimed != actual:
        raise ContractError("canonical digest mismatch")
    return actual


def _read_regular_nofollow(path):
    path = Path(path)
    fd = None
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ContractError("regular non-symlink input required")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContractError("input type changed")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("input read failure") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _physical_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _physical(path):
    return _physical_bytes(_read_regular_nofollow(path))


# Hash-bind the final R3 client before executing any of it.  Offline tests install
# their socket tripwire before importing this R4 module, therefore before this
# bound predecessor load as well.
_R3_CLIENT_PATH = ROOT / "har1r3/technical_client.py"
_R3_CLIENT_BYTES = _read_regular_nofollow(_R3_CLIENT_PATH)
if _physical_bytes(_R3_CLIENT_BYTES) != R3_TECH_CLIENT_PHYSICAL:
    raise ImportError("R3 final client physical hash mismatch")
R3_SAFETY = ModuleType("_har1r4_bound_r3_safety")
R3_SAFETY.__file__ = str(_R3_CLIENT_PATH)
exec(compile(_R3_CLIENT_BYTES, str(_R3_CLIENT_PATH), "exec"), R3_SAFETY.__dict__)


def _request_plan():
    return [
        {
            "sequence": sequence,
            "method": method,
            "url": url,
            "raw_path": raw_path,
            "body_cap_bytes": cap,
            "require_status": 200,
            "require_content_type_prefix": content_type,
            "headers": dict(headers),
        }
        for sequence, method, url, raw_path, cap, content_type, headers in REQUESTS
    ]


def _output_paths():
    return {
        "activation": ACTIVATION_PATH,
        "evidence": EVIDENCE_PATH,
        "raw": list(RAW_PATHS),
        "manifest": MANIFEST_PATH,
    }


def validate_static_files(root=ROOT):
    root = Path(root)
    files = (
        (ROUTE_PATH, ROUTE_PHYSICAL_SHA256),
        (PLAN_PATH, PLAN_PHYSICAL_SHA256),
        (CONTRACT_PATH, CONTRACT_PHYSICAL_SHA256),
    )
    documents = []
    for relative, expected in files:
        raw = _read_relative(root, relative)
        if _physical_bytes(raw) != expected:
            raise ContractError("R4 static physical drift: " + relative)
        documents.append(_strict_json(raw))
    route, plan, contract = documents
    if _canonical_digest(route, "decision_sha256", "msta-hed/sol-har1r4-source-terms-raw-route/v1") != ROUTE_CANONICAL_SHA256:
        raise ContractError("R4 route canonical drift")
    if _canonical_digest(plan, "request_plan_sha256", "msta-hed/har1r4-source-terms-request-plan/v1") != PLAN_CANONICAL_SHA256:
        raise ContractError("R4 plan canonical drift")
    if _canonical_digest(contract, "source_terms_contract_sha256", "msta-hed/har1r4-source-terms-contract/v1") != CONTRACT_CANONICAL_SHA256:
        raise ContractError("R4 contract canonical drift")
    route_fields = {
        "schema_version", "decision_id", "decision_state", "workspace_identity",
        "r3_sealed_binding", "static_creation_allowlist", "future_output_allowlist",
        "permission_matrix", "next_gate", "maximum_claim",
        "canonical_self_digest", "decision_sha256",
    }
    plan_fields = {
        "schema_version", "route_id", "route_physical_sha256",
        "route_canonical_sha256", "run_id", "activation_path", "evidence_path",
        "manifest_path", "transport", "requests", "execution_semantics",
        "canonical_self_digest", "request_plan_sha256",
    }
    contract_fields = {
        "schema_version", "route_id", "route_physical_sha256",
        "route_canonical_sha256", "request_plan_physical_sha256",
        "request_plan_canonical_sha256", "r3_replay_contract", "output_paths",
        "output_creation", "repository_validations", "terms_validation",
        "activation_contract", "readback_contract", "failure_states", "maximum_claim",
        "canonical_self_digest", "source_terms_contract_sha256",
    }
    if set(route) != route_fields or set(plan) != plan_fields or set(contract) != contract_fields:
        raise ContractError("R4 exact static schema")
    scalar = (
        route["schema_version"], route["decision_id"], route["decision_state"],
        plan["schema_version"], plan["route_id"], plan["run_id"],
        contract["schema_version"], contract["route_id"],
    )
    expected_scalar = (
        "sol-har1r4-source-terms-raw-route.v1",
        "SOL_HAR1R4_SOURCE_TERMS_RAW_EVIDENCE.v1",
        "AUTHORIZE_HAR1R4_STATIC_GATE_ONLY_NO_NETWORK",
        "har1r4-source-terms-request-plan.v1",
        "SOL_HAR1R4_SOURCE_TERMS_RAW_EVIDENCE.v1",
        RUN_ID,
        "har1r4-source-terms-contract.v1",
        "SOL_HAR1R4_SOURCE_TERMS_RAW_EVIDENCE.v1",
    )
    if scalar != expected_scalar:
        raise ContractError("R4 static identity")
    if not _exact(plan["requests"], _request_plan()) or not _exact(contract["output_paths"], _output_paths()):
        raise ContractError("R4 request/output drift")
    bindings = (
        plan["route_physical_sha256"], plan["route_canonical_sha256"],
        contract["route_physical_sha256"], contract["route_canonical_sha256"],
        contract["request_plan_physical_sha256"], contract["request_plan_canonical_sha256"],
    )
    if bindings != (
        ROUTE_PHYSICAL_SHA256, ROUTE_CANONICAL_SHA256,
        ROUTE_PHYSICAL_SHA256, ROUTE_CANONICAL_SHA256,
        PLAN_PHYSICAL_SHA256, PLAN_CANONICAL_SHA256,
    ):
        raise ContractError("R4 static cross-binding")
    transport = plan["transport"]
    expected_transport = {
        "proxy": PROXY, "concurrency": 1, "redirects": 0, "retries": 0,
        "cookies": False, "authentication": False, "api_key": False,
        "proxy_bypass": False, "per_request_network_read_timeout_seconds": 20,
        "total_network_read_budget_seconds": 80, "total_body_cap_bytes": 6029312,
    }
    if not _exact(transport, expected_transport):
        raise ContractError("R4 transport schema")
    return route, plan, contract


def _validate_bound_json(root, relative, physical, field, domain, canonical):
    raw = _read_relative(root, relative)
    if _physical_bytes(raw) != physical:
        raise ContractError("R3 physical drift: " + relative)
    document = _strict_json(raw)
    if _canonical_digest(document, field, domain) != canonical:
        raise ContractError("R3 canonical drift: " + relative)
    return document


def validate_r3_evidence_raw(raw, technical_activation):
    if type(raw) is not bytes:
        raise ContractError("R3 evidence raw bytes required")
    activation = technical_activation
    fake_capability = SimpleNamespace(
        _activation_sha256=R3_TECH_ACTIVATION_CANONICAL,
        _activation_raw_physical_sha256=R3_TECH_ACTIVATION_PHYSICAL,
        _decision_id=activation["decision_id"],
        _permission=activation["permission"],
        _bindings=activation["bindings"],
        _issued=R3_SAFETY._utc(activation["issued_at_utc"]),
        _expires=R3_SAFETY._utc(activation["expires_at_utc"]),
    )
    try:
        outcome = R3_SAFETY._readback_records(raw, fake_capability)
        lines, records = R3_SAFETY._parse_jsonl(raw)
    except Exception as exc:
        raise ContractError("R3 technical evidence replay") from exc
    if outcome != "SUCCESS" or len(lines) != 5 or len(records) != 5:
        raise ContractError("R3 technical evidence terminal")
    body = R3_SAFETY._strict_body_from_record(records[1], 1048576, "SUCCESS")
    git_blob = hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()
    body_total = sum(record.get("response_bytes", 0) for record in records[1:4])
    facts = {
        "record_count": len(records),
        "successful_probes": records[4]["successful_probes"],
        "failed_probes": records[4]["failed_probes"],
        "cumulative_elapsed_ms": records[4]["cumulative_elapsed_ms"],
        "total_response_body_bytes": body_total,
        "readme_bytes": len(body),
        "readme_sha256": hashlib.sha256(body).hexdigest(),
        "readme_git_blob_sha1": git_blob,
    }
    expected = {
        "record_count": 5, "successful_probes": 3, "failed_probes": 0,
        "cumulative_elapsed_ms": 2270, "total_response_body_bytes": 5233,
        "readme_bytes": SEALED_README_BYTES,
        "readme_sha256": SEALED_README_SHA256,
        "readme_git_blob_sha1": SEALED_README_GIT_BLOB_SHA1,
    }
    if not _exact(facts, expected):
        raise ContractError("R3 replay-derived fact mismatch")
    return facts


def replay_r3_sealed_inputs(root=ROOT):
    root = Path(root)
    route = _validate_bound_json(
        root, "config/sol_decision.har1r3-dual-lane-successor-route.v1.json",
        R3_ROUTE_PHYSICAL, "decision_sha256",
        "msta-hed/sol-har1r3-dual-lane-successor-route/v1", R3_ROUTE_CANONICAL,
    )
    technical_activation = _validate_bound_json(
        root, "config/sol_activation.har1r3-tech-reachability.v1.json",
        R3_TECH_ACTIVATION_PHYSICAL, "activation_sha256",
        "msta-hed/har1r3-technical-activation/v1", R3_TECH_ACTIVATION_CANONICAL,
    )
    terms_activation = _validate_bound_json(
        root, "config/sol_activation.har1r3-terms-evidence.v1.json",
        R3_TERMS_ACTIVATION_PHYSICAL, "activation_sha256",
        "msta-hed/har1r3-terms-evidence-activation/v1", R3_TERMS_ACTIVATION_CANONICAL,
    )
    terms_contract = _validate_bound_json(
        root, "har1r3/terms_evidence_contract.json",
        R3_TERMS_CONTRACT_PHYSICAL, "terms_evidence_contract_sha256",
        "msta-hed/har1r3-terms-evidence-contract/v1", R3_TERMS_CONTRACT_CANONICAL,
    )
    manifest = _validate_bound_json(
        root, "har1r3/terms_evidence/manifest.json",
        R3_TERMS_MANIFEST_PHYSICAL, "manifest_sha256",
        "msta-hed/har1r3-terms-evidence-manifest/v1", R3_TERMS_MANIFEST_CANONICAL,
    )
    r3_client_raw = _read_relative(root, "har1r3/technical_client.py")
    if _physical_bytes(r3_client_raw) != R3_TECH_CLIENT_PHYSICAL:
        raise ContractError("R3 technical client pre-TCP drift")
    evidence_raw = _read_relative(root, "har1r3/technical_evidence.jsonl")
    if _physical_bytes(evidence_raw) != R3_TECH_EVIDENCE_PHYSICAL or len(evidence_raw) != 13101:
        raise ContractError("R3 technical evidence physical drift")
    facts = validate_r3_evidence_raw(evidence_raw, technical_activation)
    if route["decision_id"] != "SOL_HAR1R3_DUAL_LANE_SUCCESSOR_ROUTE.v1":
        raise ContractError("R3 route identity")
    if technical_activation["decision_id"] != "SOL_HAR1R3_TECH_REACHABILITY_ACTIVATION.v1":
        raise ContractError("R3 technical activation identity")
    if terms_activation["decision_id"] != "SOL_HAR1R3_TERMS_EVIDENCE_ACTIVATION.v1":
        raise ContractError("R3 terms activation identity")
    if terms_contract["terms_evidence_contract_sha256"] != R3_TERMS_CONTRACT_CANONICAL:
        raise ContractError("R3 terms contract identity")
    if manifest.get("aggregate_status") != "SEALED_UNRESOLVED":
        raise ContractError("R3 terms manifest state")
    technical_binding = terms_activation["bindings"]["technical_evidence"]
    expected_binding = {
        "aggregate_terminal_reliable": True, "bytes": 13101,
        "cumulative_elapsed_ms": 2270, "external_evidence_state": "SEALED",
        "failed_probes": 0, "market_rows": 0,
        "path": "har1r3/technical_evidence.jsonl",
        "physical_sha256": R3_TECH_EVIDENCE_PHYSICAL,
        "protocol_outcome": "SUCCESS", "record_count": 5,
        "successful_probes": 3, "zip_body_bytes": 0,
    }
    if not _exact(technical_binding, expected_binding):
        raise ContractError("R3 terms activation technical binding")
    return facts


def _parse_utc(value):
    # Lexicographic comparison is used for evidence ordering, therefore accept
    # exactly one canonical spelling rather than the many ISO-8601 variants.
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", value):
        raise ContractError("canonical UTC millisecond timestamp required")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("invalid UTC timestamp") from exc
    return parsed.timestamp()


def _utc_now(epoch):
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        raise ContractError("local clock type")
    value = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _activation_bindings():
    return {
        "route_physical": ROUTE_PHYSICAL_SHA256,
        "route_canonical": ROUTE_CANONICAL_SHA256,
        "plan_physical": PLAN_PHYSICAL_SHA256,
        "plan_canonical": PLAN_CANONICAL_SHA256,
        "contract_physical": CONTRACT_PHYSICAL_SHA256,
        "contract_canonical": CONTRACT_CANONICAL_SHA256,
        "r3_route_physical": R3_ROUTE_PHYSICAL,
        "r3_route_canonical": R3_ROUTE_CANONICAL,
        "r3_technical_activation_physical": R3_TECH_ACTIVATION_PHYSICAL,
        "r3_technical_activation_canonical": R3_TECH_ACTIVATION_CANONICAL,
        "r3_technical_evidence_physical": R3_TECH_EVIDENCE_PHYSICAL,
        "r3_terms_activation_physical": R3_TERMS_ACTIVATION_PHYSICAL,
        "r3_terms_activation_canonical": R3_TERMS_ACTIVATION_CANONICAL,
        "r3_terms_contract_physical": R3_TERMS_CONTRACT_PHYSICAL,
        "r3_terms_contract_canonical": R3_TERMS_CONTRACT_CANONICAL,
        "r3_terms_manifest_physical": R3_TERMS_MANIFEST_PHYSICAL,
        "r3_terms_manifest_canonical": R3_TERMS_MANIFEST_CANONICAL,
        "client_physical": _physical(Path(__file__)),
        "test_physical": _physical(Path(__file__).with_name("test_source_terms_client.py")),
        "run_id": RUN_ID,
        "outputs": _output_paths(),
        "requests": _request_plan(),
    }


def _capability_factory():
    issuer = object()
    registry = {}
    issued_activations = set()
    registry_lock = threading.Lock()

    class SourceTermsCapability:
        __slots__ = (
            "_lock", "_used", "_pid", "_bindings", "_issued", "_expires",
            "_activation_sha256", "_activation_raw_physical_sha256",
            "_decision_id", "_permission",
        )

        def __init__(self, token, document, raw_physical, canonical, issued, expires):
            if token is not issuer:
                raise PermissionError("private R4 issuer required")
            self._lock, self._used, self._pid = threading.Lock(), False, os.getpid()
            self._bindings = MappingProxyType(json.loads(_canonical(document["bindings"]).decode("utf-8")))
            self._issued, self._expires = issued, expires
            self._activation_sha256, self._activation_raw_physical_sha256 = canonical, raw_physical
            self._decision_id, self._permission = document["decision_id"], document["permission"]

        def __copy__(self):
            raise PermissionError("opaque R4 capability")

        def __deepcopy__(self, _memo):
            raise PermissionError("opaque R4 capability")

        def __reduce__(self):
            raise PermissionError("opaque R4 capability")

    def issue(raw_activation, now=None):
        document = _strict_json(raw_activation)
        fields = {
            "schema_version", "decision_id", "permission", "issued_at_utc",
            "expires_at_utc", "bindings", "canonical_self_digest",
            "activation_sha256",
        }
        if set(document) != fields:
            raise ContractError("R4 activation exact schema")
        scalar = (document["schema_version"], document["decision_id"], document["permission"])
        if scalar != (
            "har1r4-source-terms-raw-activation.v1",
            "SOL_HAR1R4_SOURCE_TERMS_RAW_ACTIVATION.v1",
            "ONE_FOUR_GET_RAW_DOCUMENT_BATCH",
        ):
            raise ContractError("R4 activation identity")
        metadata = {
            "algorithm": "SHA-256_CANONICAL_JSON",
            "digest_field": "activation_sha256",
            "domain_prefix_utf8": "msta-hed/har1r4-source-terms-raw-activation/v1",
        }
        if not _exact(document["canonical_self_digest"], metadata):
            raise ContractError("R4 activation self-digest metadata")
        canonical = _canonical_digest(
            document, "activation_sha256",
            "msta-hed/har1r4-source-terms-raw-activation/v1",
        )
        raw_physical = _physical_bytes(raw_activation)
        issued, expires = _parse_utc(document["issued_at_utc"]), _parse_utc(document["expires_at_utc"])
        current = time.time() if now is None else now
        if not 0 < expires - issued <= 900:
            raise ContractError("R4 activation TTL")
        if isinstance(current, bool) or not isinstance(current, (int, float)) or not issued <= current <= expires:
            raise ContractError("R4 activation time window")
        expected = _activation_bindings()
        if not _exact(document["bindings"], expected):
            raise ContractError("R4 activation final binding")
        with registry_lock:
            if canonical in issued_activations:
                raise PermissionError("R4 activation duplicate issuance")
            capability = SourceTermsCapability(issuer, document, raw_physical, canonical, issued, expires)
            issued_activations.add(canonical)
            registry[id(capability)] = capability
        return capability

    def consume(capability, now):
        if type(capability) is not SourceTermsCapability or capability._pid != os.getpid():
            raise PermissionError("foreign or forged R4 capability")
        with registry_lock:
            if registry.get(id(capability)) is not capability:
                raise PermissionError("unissued R4 capability")
        with capability._lock:
            if capability._used or not capability._issued <= now <= capability._expires:
                raise PermissionError("R4 capability reused, premature, or expired")
            capability._used = True

    return SourceTermsCapability, issue, consume


_SourceTermsCapability, issue_activation_capability, _consume_capability = _capability_factory()


def _relative_parts(relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ContractError("safe relative path required")
    return path.parts


def _walk_parent(root, relative, create=False):
    parts = _relative_parts(relative)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    current = os.open(str(Path(root)), flags)
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o700, dir_fd=current)
                os.fsync(current)
                child = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = child
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def _relative_exists(root, relative):
    parent = None
    try:
        parent, name = _walk_parent(root, relative, create=False)
        os.stat(name, dir_fd=parent, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ContractError("unsafe output parent or target") from exc
    finally:
        if parent is not None:
            os.close(parent)


def _read_relative(root, relative):
    parent = fd = None
    try:
        parent, name = _walk_parent(root, relative, create=False)
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EvidenceReadbackError("readback nonregular")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except EvidenceReadbackError:
        raise
    except OSError as exc:
        raise EvidenceReadbackError("readonly nofollow readback") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def _write_all(fd, content):
    offset = 0
    while offset < len(content):
        written = os.write(fd, content[offset:])
        if written <= 0:
            raise OSError("partial write made no progress")
        offset += written


class _ExclusiveFile:
    def __init__(self, root, relative):
        self.root, self.relative = Path(root), relative

    def write_and_seal(self, content):
        if type(content) is not bytes:
            raise EvidenceDurabilityError("raw bytes required")
        parent = fd = None
        try:
            parent, name = _walk_parent(self.root, self.relative, create=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, 0o600, dir_fd=parent)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceDurabilityError("output nonregular")
            _write_all(fd, content)
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.fsync(parent)
        except EvidenceDurabilityError:
            raise
        except OSError as exc:
            raise EvidenceDurabilityError("create-once durability failure") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if parent is not None:
                os.close(parent)
        if _read_relative(self.root, self.relative) != content:
            raise EvidenceReadbackError("create-once readback mismatch")


class _EvidenceWriter:
    def __init__(self, root, relative=EVIDENCE_PATH):
        self.root, self.relative = Path(root), relative
        self.parent_fd, self.fd, self.previous = None, None, "0" * 64

    def prepare(self):
        if self.fd is not None:
            return
        try:
            self.parent_fd, name = _walk_parent(self.root, self.relative, create=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            self.fd = os.open(name, flags, 0o600, dir_fd=self.parent_fd)
            if not stat.S_ISREG(os.fstat(self.fd).st_mode):
                raise EvidenceDurabilityError("evidence nonregular")
            os.fsync(self.parent_fd)
        except EvidenceDurabilityError:
            self.abort()
            raise
        except OSError as exc:
            self.abort()
            raise EvidenceDurabilityError("evidence exclusive create") from exc

    def write(self, record):
        if self.fd is None:
            self.prepare()
        line = _canonical(dict(record, previous_sha256=self.previous)) + b"\n"
        try:
            _write_all(self.fd, line)
            os.fsync(self.fd)
        except OSError as exc:
            raise EvidenceDurabilityError("evidence write/fsync") from exc
        self.previous = hashlib.sha256(line).hexdigest()

    def close(self):
        if self.fd is None:
            return
        fd = self.fd
        try:
            os.close(fd)
            self.fd = None
            os.fsync(self.parent_fd)
        except OSError as exc:
            # A mocked/interrupted close may leave the descriptor live.  Make
            # one best-effort idempotent release before propagating the cause.
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None
            raise EvidenceDurabilityError("evidence close/parent fsync") from exc
        finally:
            if self.parent_fd is not None:
                parent, self.parent_fd = self.parent_fd, None
                os.close(parent)

    def abort(self):
        """Release every descriptor without hiding the triggering failure."""
        first = None
        for attribute in ("fd", "parent_fd"):
            descriptor = getattr(self, attribute)
            setattr(self, attribute, None)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    if first is None:
                        first = exc
        if first is not None:
            raise EvidenceDurabilityError("evidence abort close") from first


def _pre_tcp_recheck(capability, root=ROOT):
    root = Path(root)
    validate_static_files(root)
    replay_r3_sealed_inputs(root)
    if not _exact(dict(capability._bindings), _activation_bindings()):
        raise ContractError("R4 capability binding drift")
    try:
        activation_raw = _read_relative(root, ACTIVATION_PATH)
    except EvidenceReadbackError as exc:
        raise ContractError("R4 activation file required") from exc
    activation = _strict_json(activation_raw)
    activation_canonical = _canonical_digest(
        activation, "activation_sha256",
        "msta-hed/har1r4-source-terms-raw-activation/v1",
    )
    if _physical_bytes(activation_raw) != capability._activation_raw_physical_sha256:
        raise ContractError("R4 activation raw physical binding")
    if activation_canonical != capability._activation_sha256:
        raise ContractError("R4 activation canonical binding")
    if not _exact(activation["bindings"], dict(capability._bindings)):
        raise ContractError("R4 activation file final binding")
    for relative in (EVIDENCE_PATH, *RAW_PATHS, MANIFEST_PATH):
        if _relative_exists(root, relative):
            raise ContractError("FAIL_CLOSED_NO_OVERWRITE: " + relative)
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class _ForcedHttpsProxyHandler(urllib.request.ProxyHandler):
    def __init__(self):
        super().__init__({"https": PROXY})

    def proxy_open(self, request, proxy, protocol):
        if proxy != PROXY or protocol != "https":
            raise ContractError("fixed R4 HTTPS proxy required")
        request.set_proxy("127.0.0.1:7897", "https")
        return None


def _build_production_opener():
    return urllib.request.build_opener(_ForcedHttpsProxyHandler(), _NoRedirect())


def _production_request(sequence):
    _, method, url, _, _, _, headers = REQUESTS[sequence - 1]
    return urllib.request.Request(url, method=method, headers=headers)


def _response_status(response):
    value = getattr(response, "status", getattr(response, "code", None))
    if type(value) is not int or not 100 <= value <= 599:
        raise ProtocolViolation("HALT_PROTOCOL_VIOLATION: HTTP status")
    return value


def _header_values(response, name):
    headers = getattr(response, "headers", None)
    if headers is None:
        return []
    getter = getattr(headers, "get_all", None)
    if getter is not None:
        values = getter(name) or []
    else:
        value = headers.get(name)
        values = [] if value is None else [value]
    if any(type(value) is not str for value in values):
        raise ProtocolViolation("HALT_PROTOCOL_VIOLATION: header type")
    return values


def _close_response(response):
    close = getattr(response, "close", None)
    if close is not None:
        close()


def _visible_terms_text(body):
    class Extractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.hidden, self.parts = 0, []

        def handle_starttag(self, tag, _attrs):
            if tag.lower() in {"script", "style", "noscript", "template"}:
                self.hidden += 1

        def handle_endtag(self, tag):
            if tag.lower() in {"script", "style", "noscript", "template"} and self.hidden:
                self.hidden -= 1

        def handle_data(self, data):
            if not self.hidden:
                self.parts.append(data)

    try:
        decoded = body.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return ""
    parser = Extractor()
    try:
        parser.feed(decoded)
    except Exception:
        return ""
    return " ".join(" ".join(parser.parts).split())


def validate_terms_raw(body):
    if type(body) is not bytes or not body.strip():
        return "WAIT_DATA_TERMS_D0_DENIED"
    lower_raw = body[:200000].decode("utf-8", "ignore").lower()
    challenge_tokens = (
        "captcha", "cf-chl-", "cloudflare ray id", "verify you are human",
        "just a moment", "access denied", "security challenge", "bot detection",
    )
    if any(token in lower_raw for token in challenge_tokens):
        return "WAIT_DATA_TERMS_D0_DENIED"
    text = _visible_terms_text(body)
    lower = text.lower()
    if len(text) < 500:
        return "WAIT_DATA_TERMS_D0_DENIED"
    shell_markers = ('id="root"', "id='root'", 'id="app"', "id='app'", "__next_data__")
    if any(marker in lower_raw for marker in shell_markers) and len(text) < 1000:
        return "WAIT_DATA_TERMS_D0_DENIED"
    date_candidate = (
        re.search(r"\b20\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b", text)
        or re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+20\d{2}\b", lower)
        or re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", text)
    )
    entity_candidate = re.search(
        r"\b(?:binance|bifinity)[^\n.]{0,100}\b(?:limited|ltd\.?|inc\.?|services|holdings|japan)\b",
        lower,
    )
    jurisdiction_candidate = (
        re.search(r"\b(?:governed by|governing law|exclusive jurisdiction|courts? of|jurisdiction of)\b", lower)
        or re.search(r"(?:準拠法|管轄裁判所|裁判管轄)", text)
    )
    data_candidate = (
        re.search(r"\b(?:market data|public data|trading data|data services?)\b", lower)
        and re.search(r"\b(?:access|download|use|retain|storage|redistribut|research|derive)\w*\b", lower)
    )
    if not all((date_candidate, entity_candidate, jurisdiction_candidate, data_candidate)):
        return "WAIT_DATA_TERMS_D0_DENIED"
    return "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW"


def _parse_repo_json(body):
    return _strict_json(body)


def validate_repository_documents(repo_raw, commit_raw, tree_raw):
    mismatch = ("WAIT_DATA_SOURCE_CONTRACT_MISMATCH", None)
    try:
        repo, commit, tree = (
            _parse_repo_json(raw) for raw in (repo_raw, commit_raw, tree_raw)
        )
    except ContractError:
        return mismatch
    owner = repo.get("owner")
    commit_object = commit.get("commit")
    commit_tree_object = commit_object.get("tree") if type(commit_object) is dict else None
    if (
        type(owner) is not dict
        or type(owner.get("login")) is not str
        or owner["login"] != "binance"
        or type(repo.get("full_name")) is not str
        or repo["full_name"] != "binance/binance-public-data"
        or type(repo.get("default_branch")) is not str
        or repo["default_branch"] != "master"
        or type(commit_object) is not dict
        or type(commit_tree_object) is not dict
    ):
        return mismatch
    commit_tree = commit_tree_object.get("sha")
    tree_sha = tree.get("sha")
    sha_pattern = re.compile(r"[0-9a-f]{40}")
    if (
        type(commit_tree) is not str
        or sha_pattern.fullmatch(commit_tree) is None
        or type(tree_sha) is not str
        or sha_pattern.fullmatch(tree_sha) is None
        or commit_tree != tree_sha
        or type(tree.get("truncated")) is not bool
        or tree["truncated"] is not False
    ):
        return mismatch
    entries = tree.get("tree")
    if type(entries) is not list:
        return mismatch
    for item in entries:
        if (
            type(item) is not dict
            or type(item.get("path")) is not str
            or type(item.get("type")) is not str
            or type(item.get("sha")) is not str
            or sha_pattern.fullmatch(item["sha"]) is None
        ):
            return mismatch
    readme = [item for item in entries if item["path"] == "README.md"]
    if (
        len(readme) != 1
        or readme[0]["type"] != "blob"
        or readme[0]["sha"] != SEALED_README_GIT_BLOB_SHA1
    ):
        return mismatch
    licenses = [item for item in entries if item["path"] == "LICENSE"]
    if len(licenses) > 1 or (
        licenses and licenses[0]["type"] != "blob"
    ):
        return mismatch
    facts = {
        "owner_login": "binance",
        "full_name": "binance/binance-public-data",
        "default_branch": "master",
        "commit_tree_sha": commit_tree,
        "tree_response_sha": tree_sha,
        "readme_blob_sha1": readme[0]["sha"],
        "readme_blob_closed_to_r3_probe_1": True,
        "license_exists": bool(licenses),
        "license_disposition": "EXISTENCE_FACT_ONLY_NOT_AUTHORITY",
    }
    return "SOURCE_IDENTITY_CANDIDATE_VALIDATED", facts


def _activation_record(capability, wall_clock):
    return {
        "schema_version": "har1r4-source-terms-evidence.v1",
        "record_type": "ACTIVATION",
        "terminal": False,
        "run_id": RUN_ID,
        "decision_id": capability._decision_id,
        "permission": capability._permission,
        "activation_raw_physical_sha256": capability._activation_raw_physical_sha256,
        "activation_sha256": capability._activation_sha256,
        "issued_at_utc": _utc_now(capability._issued),
        "expires_at_utc": _utc_now(capability._expires),
        "bindings": dict(capability._bindings),
        "recorded_at_utc": _utc_now(wall_clock()),
    }


def _read_body(response, cap):
    body = response.read(cap + 1)
    if type(body) is not bytes:
        raise ProtocolViolation("HALT_PROTOCOL_VIOLATION: response body type")
    if len(body) > cap:
        raise ProtocolViolation("HALT_RESOURCE_CAP")
    return body


def _validate_response(sequence, status, content_type, final_url, body):
    expected = REQUESTS[sequence - 1]
    _, _, url, _, _, content_prefix, _ = expected
    errors = []
    if status != 200:
        errors.append("HTTP_STATUS")
    if final_url != url:
        errors.append("FINAL_URL")
    if not content_type.lower().startswith(content_prefix):
        errors.append("CONTENT_TYPE")
    if not body:
        errors.append("EMPTY_BODY")
    if sequence <= 3:
        try:
            _parse_repo_json(body)
        except ContractError:
            errors.append("JSON_BODY")
    if sequence == 4:
        disposition = validate_terms_raw(body)
        if disposition != "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW":
            errors.append(disposition)
    return errors


def _max_clock(*values):
    if not values or any(type(value) is not str for value in values):
        raise ContractError("availability local clocks")
    return max(values)


def _request_failure_record(sequence, method, url, started_at, elapsed_ms, cumulative_ms, error, wall_clock):
    observed = _utc_now(wall_clock())
    return {
        "schema_version": "har1r4-source-terms-evidence.v1",
        "record_type": "REQUEST",
        "terminal": False,
        "sequence": sequence,
        "method": method,
        "requested_url": url,
        "request_attempted": error not in {"TOTAL_NETWORK_READ_BUDGET_EXHAUSTED", "PRIOR_REQUEST_DEADLINE_EXCEEDED"},
        "outcome": "FAILURE",
        "error": error,
        "request_started_at_utc": _utc_now(started_at),
        "request_elapsed_ms": elapsed_ms,
        "cumulative_network_read_elapsed_ms": cumulative_ms,
        "raw_path": None,
        "received_at_utc": observed,
        "persisted_at_utc": observed,
        "admitted_at_utc": observed,
        "available_at_utc": observed,
    }


def _request_observation(record):
    keys = ("sequence", "request_attempted", "status_code", "content_type", "final_url", "location", "set_cookie", "request_elapsed_ms", "cumulative_network_read_elapsed_ms", "raw_path", "response_bytes", "body_sha256", "outcome", "validation_errors", "error")
    return {key: record[key] for key in keys if key in record}


def _evidence_time(value, label):
    try:
        _parse_utc(value)
    except ContractError as exc:
        raise EvidenceReadbackError(label) from exc
    return value


def _validate_evidence_readback(root, capability, expected_outcome=None, observations=None):
    """Recompute every durable fact; executor binds HTTP facts from memory.

    Raw bodies cannot independently prove status, headers, or final URL.  The
    executor therefore supplies its write-before observation ledger here; it
    is compared before a manifest can be created.
    """
    root = Path(root)
    validate_static_files(root)
    raw = _read_relative(root, EVIDENCE_PATH)
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise EvidenceReadbackError("strict JSONL framing")
    lines = raw[:-1].split(b"\n")
    if len(lines) != 6 or any(not line for line in lines):
        raise EvidenceReadbackError("exact evidence record count")
    try:
        records = [_strict_json(line) for line in lines]
    except ContractError as exc:
        raise EvidenceReadbackError("strict evidence JSON") from exc
    for line, record in zip(lines, records):
        if line != _canonical(record):
            raise EvidenceReadbackError("noncanonical evidence JSON line")
    previous = "0" * 64
    for line, record in zip(lines, records):
        if record.get("previous_sha256") != previous:
            raise EvidenceReadbackError("raw-line chain")
        previous = hashlib.sha256(line + b"\n").hexdigest()
    activation, requests, aggregate = records[0], records[1:5], records[5]
    activation_fields = {"schema_version", "record_type", "terminal", "run_id", "decision_id", "permission", "activation_raw_physical_sha256", "activation_sha256", "issued_at_utc", "expires_at_utc", "bindings", "recorded_at_utc", "previous_sha256"}
    if set(activation) != activation_fields or not _exact({key: activation.get(key) for key in ("schema_version", "record_type", "terminal", "run_id", "decision_id", "permission", "activation_raw_physical_sha256", "activation_sha256", "bindings")}, {"schema_version": "har1r4-source-terms-evidence.v1", "record_type": "ACTIVATION", "terminal": False, "run_id": RUN_ID, "decision_id": capability._decision_id, "permission": capability._permission, "activation_raw_physical_sha256": capability._activation_raw_physical_sha256, "activation_sha256": capability._activation_sha256, "bindings": dict(capability._bindings)}):
        raise EvidenceReadbackError("activation binding")
    if activation["issued_at_utc"] != _utc_now(capability._issued) or activation["expires_at_utc"] != _utc_now(capability._expires):
        raise EvidenceReadbackError("activation time binding")
    for field in ("issued_at_utc", "recorded_at_utc", "expires_at_utc"):
        _evidence_time(activation[field], "activation timestamp")
    if not activation["issued_at_utc"] <= activation["recorded_at_utc"] <= activation["expires_at_utc"]:
        raise EvidenceReadbackError("activation timestamp order")
    if [record.get("sequence") for record in requests] != [1, 2, 3, 4]:
        raise EvidenceReadbackError("request order")
    if observations is not None and len(observations) != 4:
        raise EvidenceReadbackError("live observation count")
    previous_cumulative, previous_available, bodies, deadline_seen = 0, activation["recorded_at_utc"], {}, False
    for index, (record, expected) in enumerate(zip(requests, REQUESTS)):
        sequence, method, url, raw_path, cap, _, _ = expected
        base = {"schema_version", "record_type", "terminal", "sequence", "method", "requested_url", "request_attempted", "outcome", "request_started_at_utc", "request_elapsed_ms", "cumulative_network_read_elapsed_ms", "raw_path", "received_at_utc", "persisted_at_utc", "admitted_at_utc", "available_at_utc", "previous_sha256"}
        response = {"final_url", "validation_errors", "status_code", "content_type", "location", "set_cookie", "set_cookie_reused", "response_bytes", "body_sha256"}
        if set(record) != base | (response if record.get("raw_path") is not None else {"error"}):
            raise EvidenceReadbackError("request exact schema")
        if (type(record.get("terminal")) is not bool or type(record.get("sequence")) is not int or record.get("terminal") is not False or record.get("sequence") != sequence or (record.get("schema_version"), record.get("record_type"), record.get("method"), record.get("requested_url")) != ("har1r4-source-terms-evidence.v1", "REQUEST", method, url)):
            raise EvidenceReadbackError("request identity")
        if type(record["request_attempted"]) is not bool or record["outcome"] not in {"SUCCESS", "FAILURE"} or any(type(record[k]) is not int or record[k] < 0 for k in ("request_elapsed_ms", "cumulative_network_read_elapsed_ms")):
            raise EvidenceReadbackError("request type")
        elapsed, cumulative = record["request_elapsed_ms"], record["cumulative_network_read_elapsed_ms"]
        remaining = max(0, 80000 - previous_cumulative)
        if cumulative != previous_cumulative + elapsed or cumulative > 80000:
            raise EvidenceReadbackError("deterministic network budget")
        if remaining == 0:
            if not (record["request_attempted"] is False and record["raw_path"] is None and record.get("error") == "TOTAL_NETWORK_READ_BUDGET_EXHAUSTED" and elapsed == 0):
                raise EvidenceReadbackError("budget exhausted request")
        elif deadline_seen:
            if not (record["request_attempted"] is False and record["raw_path"] is None and record.get("error") == "PRIOR_REQUEST_DEADLINE_EXCEEDED" and elapsed == 0):
                raise EvidenceReadbackError("post-deadline request")
        elif record["request_attempted"] is False and record.get("error") in {"TOTAL_NETWORK_READ_BUDGET_EXHAUSTED", "PRIOR_REQUEST_DEADLINE_EXCEEDED"}:
            raise EvidenceReadbackError("unlatched budget/deadline marker")
        previous_cumulative = cumulative
        if record.get("raw_path") is not None:
            if record["raw_path"] != raw_path or record["request_attempted"] is not True or type(record["status_code"]) is not int or not 100 <= record["status_code"] <= 599 or type(record["content_type"]) is not str or type(record["final_url"]) is not str or type(record["location"]) is not list or type(record["set_cookie"]) is not list or any(type(x) is not str for x in record["location"] + record["set_cookie"]) or record["set_cookie_reused"] is not False or type(record["validation_errors"]) is not list or any(type(x) is not str for x in record["validation_errors"]) or type(record.get("response_bytes")) is not int:
                raise EvidenceReadbackError("response evidence type")
            body = _read_relative(root, raw_path)
            if len(body) > cap or len(body) != record["response_bytes"] or hashlib.sha256(body).hexdigest() != record["body_sha256"]:
                raise EvidenceReadbackError("raw body derivation")
            errors = _validate_response(sequence, record["status_code"], record["content_type"], record["final_url"], body)
            assigned = min(20000, max(0, 80000 - (cumulative - elapsed)))
            if elapsed >= assigned:
                errors.append("REQUEST_DEADLINE_EXCEEDED_AFTER_RETURN")
            if cumulative >= 80000:
                errors.append("TOTAL_NETWORK_READ_DEADLINE_EXCEEDED_AFTER_RETURN")
            if record["validation_errors"] != errors or record["outcome"] != ("SUCCESS" if not errors else "FAILURE"):
                raise EvidenceReadbackError("response validation derivation")
            if elapsed >= assigned:
                deadline_seen = True
            bodies[sequence] = body
        else:
            unattempted = {"TOTAL_NETWORK_READ_BUDGET_EXHAUSTED", "PRIOR_REQUEST_DEADLINE_EXCEEDED"}
            if type(record.get("error")) is not str or not record["error"] or record["outcome"] != "FAILURE" or (record["request_attempted"] is False) != (record["error"] in unattempted) or _relative_exists(root, raw_path):
                raise EvidenceReadbackError("transport failure derivation")
            if record["request_attempted"] is True and (
                elapsed >= min(20000, remaining)
                or record["error"] == "REQUEST_DEADLINE_EXCEEDED"
            ):
                deadline_seen = True
        for field in ("request_started_at_utc", "received_at_utc", "persisted_at_utc", "admitted_at_utc", "available_at_utc"):
            _evidence_time(record[field], "request timestamp")
        if not previous_available <= record["request_started_at_utc"] <= record["received_at_utc"] <= record["persisted_at_utc"] <= record["admitted_at_utc"] or record["available_at_utc"] != max(record["received_at_utc"], record["persisted_at_utc"], record["admitted_at_utc"]):
            raise EvidenceReadbackError("request timestamp order")
        previous_available = record["available_at_utc"]
        if observations is not None and not _exact(_request_observation(record), observations[index]):
            raise EvidenceReadbackError("live transport observation mismatch")
    aggregate_fields = {"schema_version", "record_type", "terminal", "outcome", "request_results", "successful_requests", "failed_requests", "cumulative_network_read_elapsed_ms", "repository_state", "terms_state", "legal_conclusion", "recorded_at_utc", "previous_sha256"}
    if set(aggregate) != aggregate_fields or type(aggregate.get("terminal")) is not bool or type(aggregate.get("legal_conclusion")) is not bool or any(type(aggregate.get(field)) is not int for field in ("successful_requests", "failed_requests", "cumulative_network_read_elapsed_ms")) or (aggregate.get("schema_version"), aggregate.get("record_type"), aggregate.get("terminal"), aggregate.get("legal_conclusion")) != ("har1r4-source-terms-evidence.v1", "AGGREGATE_TERMINAL", True, False):
        raise EvidenceReadbackError("aggregate schema")
    results = [{"sequence": r["sequence"], "outcome": r["outcome"], "request_attempted": r["request_attempted"]} for r in requests]
    successes = sum(r["outcome"] == "SUCCESS" for r in requests)
    repository_state, repository_facts = ("WAIT_DATA_SOURCE_CONTRACT_MISMATCH", None)
    if all(n in bodies for n in (1, 2, 3)):
        repository_state, repository_facts = validate_repository_documents(bodies[1], bodies[2], bodies[3])
    terms_state = validate_terms_raw(bodies[4]) if 4 in bodies else "WAIT_DATA_TERMS_D0_DENIED"
    outcome = "SUCCESS" if successes == 4 and repository_state == "SOURCE_IDENTITY_CANDIDATE_VALIDATED" and terms_state == "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW" else "FAILURE"
    if not _exact(aggregate["request_results"], results) or aggregate["successful_requests"] != successes or aggregate["failed_requests"] != 4 - successes or aggregate["cumulative_network_read_elapsed_ms"] != previous_cumulative or aggregate["repository_state"] != repository_state or aggregate["terms_state"] != terms_state or aggregate["outcome"] != outcome:
        raise EvidenceReadbackError("aggregate derivation")
    _evidence_time(aggregate["recorded_at_utc"], "aggregate timestamp")
    if aggregate["recorded_at_utc"] < previous_available:
        raise EvidenceReadbackError("aggregate timestamp order")
    if expected_outcome is not None and aggregate["outcome"] != expected_outcome:
        raise EvidenceReadbackError("aggregate expected outcome")
    return records


def _manifest_document(root, capability, records, repository_state, repository_facts, terms_state, wall_clock):
    aggregate = records[-1]
    document = {
        "schema_version": "har1r4-source-terms-manifest.v1",
        "run_id": RUN_ID,
        "activation_raw_physical_sha256": capability._activation_raw_physical_sha256,
        "activation_sha256": capability._activation_sha256,
        "evidence_path": EVIDENCE_PATH,
        "evidence_physical_sha256": hashlib.sha256(_read_relative(root, EVIDENCE_PATH)).hexdigest(),
        "request_results": [
            {
                "sequence": record["sequence"],
                "outcome": record["outcome"],
                "status_code": record.get("status_code"),
                "raw_path": record.get("raw_path"),
                "body_sha256": record.get("body_sha256"),
                "available_at_utc": record["available_at_utc"],
            }
            for record in records[1:5]
        ],
        "repository_state": repository_state,
        "repository_facts": repository_facts,
        "terms_state": terms_state,
        "legal_conclusion": False,
        "aggregate_outcome": aggregate["outcome"],
        "completed_at_utc": _utc_now(wall_clock()),
        "canonical_self_digest": {
            "algorithm": "SHA-256_CANONICAL_JSON",
            "digest_field": "manifest_sha256",
            "domain_prefix_utf8": "msta-hed/har1r4-source-terms-manifest/v1",
        },
    }
    unsigned = dict(document)
    document["manifest_sha256"] = hashlib.sha256(
        b"msta-hed/har1r4-source-terms-manifest/v1\0" + _canonical(unsigned)
    ).hexdigest()
    return document


def _validate_manifest_readback(root, capability, observations):
    """Validate a manifest only with the same-run live observation ledger."""
    if observations is None:
        raise EvidenceReadbackError("manifest requires live observations")
    records = _validate_evidence_readback(
        root, capability, observations=observations
    )
    raw = _read_relative(root, MANIFEST_PATH)
    document = _strict_json(raw)
    if raw != _canonical(document):
        raise EvidenceReadbackError("manifest noncanonical physical bytes")
    fields = {
        "schema_version", "run_id", "activation_raw_physical_sha256", "activation_sha256",
        "evidence_path", "evidence_physical_sha256", "request_results", "repository_state",
        "repository_facts", "terms_state", "legal_conclusion", "aggregate_outcome",
        "completed_at_utc", "canonical_self_digest", "manifest_sha256",
    }
    metadata = {"algorithm": "SHA-256_CANONICAL_JSON", "digest_field": "manifest_sha256", "domain_prefix_utf8": "msta-hed/har1r4-source-terms-manifest/v1"}
    if set(document) != fields or not _exact(document.get("canonical_self_digest"), metadata):
        raise EvidenceReadbackError("manifest exact schema")
    _canonical_digest(document, "manifest_sha256", "msta-hed/har1r4-source-terms-manifest/v1")
    aggregate = records[-1]
    bodies = {}
    for record, raw_path in zip(records[1:5], RAW_PATHS):
        if record["raw_path"] is not None:
            bodies[record["sequence"]] = _read_relative(root, raw_path)
    repository_state, repository_facts = "WAIT_DATA_SOURCE_CONTRACT_MISMATCH", None
    if all(sequence in bodies for sequence in (1, 2, 3)):
        repository_state, repository_facts = validate_repository_documents(
            bodies[1], bodies[2], bodies[3]
        )
    terms_state = validate_terms_raw(bodies[4]) if 4 in bodies else "WAIT_DATA_TERMS_D0_DENIED"
    if (
        aggregate["repository_state"] != repository_state
        or aggregate["terms_state"] != terms_state
    ):
        raise EvidenceReadbackError("manifest current raw aggregate mismatch")
    expected = _manifest_document(
        root, capability, records, repository_state, repository_facts, terms_state,
        lambda: _parse_utc(document["completed_at_utc"]),
    )
    # Only completed_at comes from wall clock; all content must be recomputed.
    if not _exact(document, expected):
        raise EvidenceReadbackError("manifest derived binding")
    _evidence_time(document["completed_at_utc"], "manifest timestamp")
    if document["completed_at_utc"] < aggregate["recorded_at_utc"]:
        raise EvidenceReadbackError("manifest timestamp order")
    return document, records


def _execute_with_transport(
    capability, transport, root, monotonic, wall_clock,
    deadline_factory=None, evidence_writer_factory=_EvidenceWriter,
):
    root = Path(root)
    _consume_capability(capability, wall_clock())
    _pre_tcp_recheck(capability, root)
    writer = evidence_writer_factory(root)
    try:
        writer.write(_activation_record(capability, wall_clock))
    except Exception:
        try:
            writer.abort()
        except Exception:
            pass
        raise
    network_elapsed, stop_after_deadline = 0, False
    request_records, bodies, observations = [], {}, []
    try:
        for sequence, method, url, raw_path, cap, _, headers in REQUESTS:
            started_at, start_tick = wall_clock(), monotonic()
            if network_elapsed >= 80000:
                record = _request_failure_record(
                    sequence, method, url, started_at, 0, network_elapsed,
                    "TOTAL_NETWORK_READ_BUDGET_EXHAUSTED", wall_clock,
                )
                writer.write(record)
                request_records.append(record)
                observations.append(_request_observation(record))
                continue
            if stop_after_deadline:
                record = _request_failure_record(
                    sequence, method, url, started_at, 0, network_elapsed,
                    "PRIOR_REQUEST_DEADLINE_EXCEEDED", wall_clock,
                )
                writer.write(record)
                request_records.append(record)
                observations.append(_request_observation(record))
                continue
            timeout = min(20.0, (80000 - network_elapsed) / 1000.0)
            response, status, body, content_type, final_url = None, None, None, "", None
            response_closed = False
            location, set_cookie, error, deadline_exception = [], [], None, False
            # Guard construction/entry is a control-plane prerequisite.  It
            # must never be recoded as an ordinary network transport failure.
            guard = None
            if deadline_factory is not None:
                guard = deadline_factory(timeout)
                guard.__enter__()
            try:
                def execute():
                    nonlocal response, status, body, content_type, final_url, location, set_cookie, response_closed
                    try:
                        response = transport(method, url, timeout, dict(headers))
                    except urllib.error.HTTPError as exc:
                        response = exc
                    status = _response_status(response)
                    content_values = _header_values(response, "Content-Type")
                    content_type = content_values[0] if content_values else ""
                    location = _header_values(response, "Location")
                    set_cookie = _header_values(response, "Set-Cookie")
                    final_url = response.geturl()
                    try:
                        body = _read_body(response, cap)
                    finally:
                        closing, response = response, None
                        _close_response(closing)
                        response_closed = True
                execute()
            except ProtocolViolation:
                if response is not None:
                    try:
                        _close_response(response)
                    finally:
                        response = None
                raise
            except Exception as exc:
                deadline_type = R3_SAFETY.R2_SAFETY._DeadlineExceeded
                deadline_exception = type(exc) is deadline_type
                error = "REQUEST_DEADLINE_EXCEEDED" if deadline_exception else type(exc).__name__
                if not response_closed:
                    body = None
                if response is not None:
                    try:
                        _close_response(response)
                    finally:
                        response = None
            finally:
                if guard is not None:
                    guard.__exit__(None, None, None)
            elapsed = max(0.0, monotonic() - start_tick)
            elapsed_ms = max(0, int(elapsed * 1000))
            assigned_ms = min(20000, 80000 - network_elapsed)
            # A deadline hit is durable evidence of failure.  No later request may
            # be attempted, so it cannot be disguised by a fresh budget.
            deadline_hit = deadline_exception or elapsed_ms >= assigned_ms
            network_elapsed += elapsed_ms
            received = _utc_now(wall_clock())
            if body is not None:
                if deadline_hit and error is None:
                    error = "REQUEST_DEADLINE_EXCEEDED_AFTER_RETURN"
                if network_elapsed >= 80000 and error is None:
                    error = "TOTAL_NETWORK_READ_DEADLINE_EXCEEDED_AFTER_RETURN"
                _ExclusiveFile(root, raw_path).write_and_seal(body)
                persisted = _utc_now(wall_clock())
                errors = _validate_response(sequence, status, content_type, final_url, body)
                if error is not None:
                    errors.append(error)
                admitted = _utc_now(wall_clock())
                outcome = "SUCCESS" if not errors else "FAILURE"
                record = {
                    "schema_version": "har1r4-source-terms-evidence.v1",
                    "record_type": "REQUEST",
                    "terminal": False,
                    "sequence": sequence,
                    "method": method,
                    "requested_url": url,
                    "final_url": final_url,
                    "request_attempted": True,
                    "outcome": outcome,
                    "validation_errors": errors,
                    "status_code": status,
                    "content_type": content_type,
                    "location": location,
                    "set_cookie": set_cookie,
                    "set_cookie_reused": False,
                    "request_started_at_utc": _utc_now(started_at),
                    "request_elapsed_ms": elapsed_ms,
                    "cumulative_network_read_elapsed_ms": network_elapsed,
                    "raw_path": raw_path,
                    "response_bytes": len(body),
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "received_at_utc": received,
                    "persisted_at_utc": persisted,
                    "admitted_at_utc": admitted,
                    "available_at_utc": _max_clock(received, persisted, admitted),
                }
                bodies[sequence] = body
            else:
                record = _request_failure_record(
                    sequence, method, url, started_at, elapsed_ms, network_elapsed,
                    error or "WAIT_DATA_NETWORK_TRANSPORT", wall_clock,
                )
            writer.write(record)
            request_records.append(record)
            observations.append(_request_observation(record))
            if deadline_hit:
                stop_after_deadline = True
        repository_state, repository_facts = "WAIT_DATA_SOURCE_CONTRACT_MISMATCH", None
        if all(sequence in bodies for sequence in (1, 2, 3)):
            repository_state, repository_facts = validate_repository_documents(
                bodies[1], bodies[2], bodies[3]
            )
        terms_state = validate_terms_raw(bodies[4]) if 4 in bodies else "WAIT_DATA_TERMS_D0_DENIED"
        protocol_success = (
            all(record["outcome"] == "SUCCESS" for record in request_records)
            and repository_state == "SOURCE_IDENTITY_CANDIDATE_VALIDATED"
            and terms_state == "CANDIDATE_TEXT_ONLY_REQUIRES_INDEPENDENT_REVIEW"
        )
        aggregate = {
            "schema_version": "har1r4-source-terms-evidence.v1",
            "record_type": "AGGREGATE_TERMINAL",
            "terminal": True,
            "outcome": "SUCCESS" if protocol_success else "FAILURE",
            "request_results": [
                {
                    "sequence": record["sequence"],
                    "outcome": record["outcome"],
                    "request_attempted": record["request_attempted"],
                }
                for record in request_records
            ],
            "successful_requests": sum(record["outcome"] == "SUCCESS" for record in request_records),
            "failed_requests": sum(record["outcome"] == "FAILURE" for record in request_records),
            "cumulative_network_read_elapsed_ms": network_elapsed,
            "repository_state": repository_state,
            "terms_state": terms_state,
            "legal_conclusion": False,
            "recorded_at_utc": _utc_now(wall_clock()),
        }
        writer.write(aggregate)
        writer.close()
        records = _validate_evidence_readback(root, capability, aggregate["outcome"], observations)
        manifest = _manifest_document(
            root, capability, records, repository_state, repository_facts, terms_state, wall_clock
        )
        raw_manifest = _canonical(manifest)
        _ExclusiveFile(root, MANIFEST_PATH).write_and_seal(raw_manifest)
        readback_manifest, readback_records = _validate_manifest_readback(
            root, capability, observations
        )
        return {
            "external_evidence_state": "SEALED",
            "protocol_outcome": readback_records[-1]["outcome"],
            "manifest_sha256": readback_manifest["manifest_sha256"],
        }
    except Exception:
        try:
            writer.abort()
        except Exception:
            pass
        raise


def execute_source_terms_raw(capability):
    """Future production entry; requires a separately issued Sol activation."""
    # Alarm availability is a production precondition, not a transport error.
    # It runs before opener construction, capability consumption, or any output.
    R3_SAFETY._require_production_alarm_available()
    opener = _build_production_opener()

    def transport(method, url, timeout, headers):
        request = urllib.request.Request(url, method=method, headers=headers)
        return opener.open(request, timeout=timeout)

    return _execute_with_transport(
        capability, transport, ROOT, time.monotonic, time.time,
        deadline_factory=R3_SAFETY._posix_deadline,
    )
