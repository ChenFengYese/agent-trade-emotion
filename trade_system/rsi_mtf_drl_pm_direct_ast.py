"""External conformance checks for direct-machine-AST review slices.

This module is deliberately outside the AST: a candidate cannot validate itself.
It implements only the profile's ASCII/safe-integer/RFC8785 subset and local
slice checks; full graph closure belongs to the whole-AST review gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SAFE_INT_MIN = -9007199254740991
SAFE_INT_MAX = 9007199254740991
NODE_ID_RE = re.compile(r"^(type|schema|const|algorithm|identity|routing)/[A-Za-z][A-Za-z0-9_.-]*$")
FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONST_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
PROFILE_SHA256 = "4971a337605b7d3bbfdae3657a47498c2cfeb2d055f0e861339c57e02968aa48"
SEMANTIC_SOURCE_SHA256 = "43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6"
PROFILE_SIZE_BYTES = 82244
SEMANTIC_SOURCE_SIZE_BYTES = 136468
NODE_VERSION = "rsi-mtf-drl-pm.direct-node.v0.2.2"
LITERAL_REGISTRY = "const/LiteralRegistry.v0.2.2"
FORBIDDEN_KEYS = {"description", "comment", "section", "line", "source_pointer", "unchanged", "inherit", "default", "TODO", "TBD", "ellipsis"}
KIND_BY_PREFIX = {"type": "TYPE", "schema": "SCHEMA", "const": "CONST", "algorithm": "ALGORITHM", "identity": "IDENTITY", "routing": "ROUTING"}
DECIMAL_KIND_SYMBOLS = {
    "BPS": "DECIMAL_KIND_BPS",
    "DECIMAL": "DECIMAL_KIND_DECIMAL",
    "MONEY": "DECIMAL_KIND_MONEY",
    "PRICE": "DECIMAL_KIND_PRICE",
    "QTY_BASE": "DECIMAL_KIND_QTY_BASE",
}
MARKET_SOURCE_VARIANTS = [
    ["T_OBJECT", "schema/AggTrade.v0.2.2"],
    ["T_OBJECT", "schema/BookSnapshot.v0.2.2"],
    ["T_OBJECT", "schema/ClosedMarkBar.v0.2.2"],
    ["T_OBJECT", "schema/OpenInterest.v0.2.2"],
]


def _selector_return(status_symbols: list[str], schema: str) -> list[Any]:
    return ["T_UNION", [["T_ENUM", [["CONST_REF", LITERAL_REGISTRY, symbol] for symbol in status_symbols]], ["T_OBJECT", schema]]]


SELECTOR_RETURNS = {
    "algorithm/SelectCoverageSeal.v0.2.2": _selector_return(["SELECTOR_COVERAGE_CONFLICT", "SELECTOR_UNKNOWN"], "schema/CoverageSeal.v0.2.2"),
    "algorithm/SelectBook.v0.2.2": _selector_return(["SELECTOR_CONFLICT", "SELECTOR_UNKNOWN"], "schema/BookSnapshot.v0.2.2"),
    "algorithm/SelectOpenInterest.v0.2.2": _selector_return(["SELECTOR_CONFLICT", "SELECTOR_UNKNOWN"], "schema/OpenInterest.v0.2.2"),
    "algorithm/SelectVenueSnapshot.v0.2.2": _selector_return(["SELECTOR_RULE_SNAPSHOT_CONFLICT", "SELECTOR_UNKNOWN"], "schema/VenueInstrumentSnapshot.v0.2.2"),
    "algorithm/SelectAccountSnapshot.v0.2.2": _selector_return(["SELECTOR_ACCOUNT_SNAPSHOT_CONFLICT", "SELECTOR_UNKNOWN"], "schema/AccountRiskSnapshot.v0.2.2"),
    "algorithm/SelectClosedMarkBarSlot.v0.2.2": _selector_return(["SELECTOR_CONFLICT", "SELECTOR_UNKNOWN"], "schema/ClosedMarkBar.v0.2.2"),
    "algorithm/SelectBookGrid.v0.2.2": _selector_return(["SELECTOR_CONFLICT", "SELECTOR_UNKNOWN"], "schema/BookSnapshot.v0.2.2"),
    "algorithm/SelectAggTradeWindow.v0.2.2": ["T_UNION", [["T_ARRAY", ["T_OBJECT", "schema/AggTrade.v0.2.2"], 0, None, True, {"directions": ["ASC", "ASC", "ASC"], "keys": [[["FIELD", "event_time_us"]], [["FIELD", "source_sequence"]], [["FIELD", "event_id"]]], "nulls": ["FORBIDDEN", "FORBIDDEN", "FORBIDDEN"]}], ["T_ENUM", [["CONST_REF", LITERAL_REGISTRY, "SELECTOR_COVERAGE_CONFLICT"], ["CONST_REF", LITERAL_REGISTRY, "SELECTOR_UNKNOWN"]]]]],
}


class ASTReject(ValueError):
    """The candidate fails a deterministic AST/profile rule."""


def validate_authority_files(repo_root: Path) -> None:
    """Fail closed unless the two inputs named by this review slice are exact."""
    expected = {
        "archive/authority/RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md": (PROFILE_SIZE_BYTES, PROFILE_SHA256),
        "archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md": (SEMANTIC_SOURCE_SIZE_BYTES, SEMANTIC_SOURCE_SHA256),
    }
    for relative, (size, digest) in expected.items():
        raw = (repo_root / relative).read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ASTReject(f"immutable authority mismatch: {relative}")


def _ascii(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.isascii():
        raise ASTReject(f"{label} must be ASCII")


def _safe_int(value: Any, label: str) -> None:
    if type(value) is not int or not SAFE_INT_MIN <= value <= SAFE_INT_MAX:
        raise ASTReject(f"{label} must be a safe integer")


def _walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for key, item in value.items():
            _ascii(key, "object key")
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)
    elif isinstance(value, str):
        _ascii(value, "wire string")
    elif type(value) is int:
        _safe_int(value, "integer")
    elif isinstance(value, float):
        raise ASTReject("JSON float is forbidden")
    elif value is not None and type(value) is not bool:
        raise ASTReject("unsupported JSON scalar")


def canonical_json(value: Any) -> bytes:
    """Profile §2's ASCII-only RFC8785 subset, compact UTF-8 without LF."""
    list(_walk_json(value))
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ASTReject(f"not canonical JSON: {exc}") from exc
    return encoded.encode("ascii")


def identity(domain_ascii: str, preimage: Any) -> str:
    _ascii(domain_ascii, "identity domain")
    return hashlib.sha256(domain_ascii.encode("ascii") + b"\0" + canonical_json(preimage)).hexdigest()


def node_digest(node_id: str, envelope: dict[str, Any]) -> str:
    return identity("rsi-mtf-drl-pm-direct-node/v0.2.2", {"node_envelope": envelope, "node_id": node_id})


def load_slice(path: Path) -> dict[str, dict[str, Any]]:
    raw = path.read_bytes()
    if raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise ASTReject("slice bytes must be UTF-8 without BOM or trailing newline")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ASTReject(f"invalid JSON: {exc}") from exc
    if canonical_json(parsed) != raw:
        raise ASTReject("slice is not canonical compact UTF-8 JSON")
    if type(parsed) is not dict or set(parsed) != {"nodes"} or type(parsed["nodes"]) is not dict:
        raise ASTReject("slice root must be exact {nodes}")
    return parsed["nodes"]


def _const_ref(value: Any, registry: dict[str, Any]) -> None:
    if not (isinstance(value, list) and len(value) == 3 and value[0] == "CONST_REF" and value[1] == LITERAL_REGISTRY and isinstance(value[2], str) and CONST_RE.fullmatch(value[2])):
        raise ASTReject("invalid ConstRef")
    if value[2] not in registry:
        raise ASTReject("ConstRef member missing from literal registry")


def _node_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "schema_node_id" and isinstance(item, str):
                refs.add(item)
            _node_refs(item, refs)
        return
    if not isinstance(value, list):
        return
    if value and value[0] in {"T_REF", "T_OBJECT", "CALL", "TYPE_VALID", "OBJECT", "IDENTITY_EVAL"} and len(value) > 1 and isinstance(value[1], str):
        refs.add(value[1])
    if value and value[0] == "CONST_REF" and len(value) > 1 and isinstance(value[1], str):
        refs.add(value[1])
    for item in value:
        _node_refs(item, refs)


def _reject_raw_identity(value: Any) -> None:
    """`ID(domain, value)` is not an AST expression; only IDENTITY_EVAL may occur."""
    if isinstance(value, dict):
        for item in value.values():
            _reject_raw_identity(item)
    elif isinstance(value, list):
        if value and value[0] == "ID":
            raise ASTReject("raw ID expression is forbidden; use IDENTITY_EVAL")
        for item in value:
            _reject_raw_identity(item)


def _check_new_profile_constructs(value: Any, registry: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _check_new_profile_constructs(item, registry)
        return
    if not isinstance(value, list):
        return
    if value:
        opcode = value[0]
        if isinstance(opcode, str) and opcode in {"DECIMAL_VALID", "DECIMAL_PARSE"}:
            if len(value) != 3 or value[1] not in DECIMAL_KIND_SYMBOLS:
                raise ASTReject(f"{opcode} must carry an exact DecimalKind")
        elif opcode == "DECIMAL_FORMAT" and len(value) != 2:
            raise ASTReject("DECIMAL_FORMAT shape")
        elif opcode == "DECIMAL" and (len(value) != 3 or value[1] not in DECIMAL_KIND_SYMBOLS or not isinstance(value[2], str)):
            raise ASTReject("DECIMAL literal shape")
        elif opcode == "MATCH_NARROW":
            if len(value) != 3 or not isinstance(value[2], list) or not value[2]:
                raise ASTReject("MATCH_NARROW shape")
            for case in value[2]:
                if not isinstance(case, dict) or set(case) != {"bind", "statements", "type"} or not isinstance(case["bind"], str) or not FIELD_RE.fullmatch(case["bind"]) or not isinstance(case["statements"], list):
                    raise ASTReject("MATCH_NARROW case shape")
                _check_type_expr(case["type"], registry)
    for item in value:
        _check_new_profile_constructs(item, registry)


def _check_type_expr(value: Any, registry: dict[str, Any], in_bytes_node: bool = False, algorithm_context: bool = False) -> None:
    if not isinstance(value, list) or not value or not isinstance(value[0], str):
        raise ASTReject("TypeExpr must be a closed opcode array")
    op = value[0]
    if op == "T_REF":
        if len(value) != 2 or not isinstance(value[1], str) or not NODE_ID_RE.fullmatch(value[1]) or value[1].split("/", 1)[0] != "type":
            raise ASTReject("T_REF must target TYPE")
    elif op == "T_OBJECT":
        if len(value) != 2 or not isinstance(value[1], str) or not value[1].startswith("schema/"):
            raise ASTReject("T_OBJECT must target SCHEMA")
    elif op == "T_PRIMITIVE":
        if len(value) != 2 or value[1] not in {"STRING", "INTEGER", "BOOLEAN", "NULL", "ANY_JSON", "BYTES"}:
            raise ASTReject("invalid primitive")
        if value[1] == "BYTES" and not in_bytes_node:
            raise ASTReject("BYTES wire use is forbidden")
    elif op == "T_DECIMAL_VALUE":
        if len(value) != 2 or value[1] not in DECIMAL_KIND_SYMBOLS:
            raise ASTReject("invalid T_DECIMAL_VALUE DecimalKind")
        if not algorithm_context:
            raise ASTReject("T_DECIMAL_VALUE is evaluator-only and allowed only in ALGORITHM signatures")
    elif op == "T_CONST_REF":
        if len(value) != 2:
            raise ASTReject("T_CONST_REF shape")
        _const_ref(value[1], registry)
    elif op == "T_ENUM":
        if len(value) != 2 or not isinstance(value[1], list) or not value[1]:
            raise ASTReject("T_ENUM shape")
        for ref in value[1]:
            _const_ref(ref, registry)
    elif op == "T_ARRAY":
        if len(value) != 6:
            raise ASTReject("T_ARRAY shape")
        _check_type_expr(value[1], registry, algorithm_context=algorithm_context)
        _safe_int(value[2], "array min")
        if value[3] is not None:
            _safe_int(value[3], "array max")
    elif op == "T_MAP":
        if len(value) != 6 or value[5] != "UTF8_BYTES_ASC":
            raise ASTReject("T_MAP shape/order")
        _check_type_expr(value[1], registry, algorithm_context=algorithm_context)
        _check_type_expr(value[2], registry, algorithm_context=algorithm_context)
    elif op == "T_UNION":
        if len(value) != 2 or not isinstance(value[1], list) or len(value[1]) < 2:
            raise ASTReject("T_UNION shape")
        for item in value[1]:
            _check_type_expr(item, registry, algorithm_context=algorithm_context)
    elif op in {"T_NULLABLE", "T_CONSTRAINED"}:
        if len(value) != 2 if op == "T_NULLABLE" else len(value) != 3:
            raise ASTReject(f"{op} shape")
        _check_type_expr(value[1], registry, algorithm_context=algorithm_context)
    else:
        raise ASTReject("unknown TypeExpr opcode")


def _check_body(node_id: str, kind: str, body: Any, registry: dict[str, Any]) -> None:
    if not isinstance(body, dict):
        raise ASTReject("node body must be an object")
    if FORBIDDEN_KEYS.intersection(body):
        raise ASTReject("forbidden prose/source key in node body")
    _reject_raw_identity(body)
    _check_new_profile_constructs(body, registry)
    if kind == "TYPE":
        if set(body) != {"type_expr"}:
            raise ASTReject("TYPE exact body keys")
        _check_type_expr(body["type_expr"], registry, node_id == "type/Bytes")
        nominal = {
            "type/DecimalString": "DECIMAL",
            "type/QtyBase": "QTY_BASE",
            "type/Price": "PRICE",
            "type/Money": "MONEY",
            "type/Bps": "BPS",
        }.get(node_id)
        if nominal is not None:
            expected = ["T_CONSTRAINED", ["T_PRIMITIVE", "STRING"], [["CALL", "algorithm/ValidateDecimal.v0.2.2", {"kind": ["CONST", ["CONST_REF", LITERAL_REGISTRY, DECIMAL_KIND_SYMBOLS[nominal]]], "value": ["GET", "$self", []]}]]]
            if body["type_expr"] != expected:
                raise ASTReject("nominal decimal TYPE body must be profile-exact")
        if node_id == "type/MarketSourceObject" and body["type_expr"] != ["T_UNION", MARKET_SOURCE_VARIANTS]:
            raise ASTReject("MarketSourceObject must be profile-exact union")
    elif kind == "SCHEMA":
        if set(body) != {"exact_keys", "properties", "constraints"}:
            raise ASTReject("SCHEMA exact body keys")
        keys, props = body["exact_keys"], body["properties"]
        if not isinstance(keys, list) or keys != sorted(keys) or len(keys) != len(set(keys)) or not isinstance(props, dict) or set(keys) != set(props):
            raise ASTReject("schema exact_keys/properties mismatch")
        for key, typ in props.items():
            if not FIELD_RE.fullmatch(key):
                raise ASTReject("invalid schema property name")
            _check_type_expr(typ, registry)
        if not isinstance(body["constraints"], list):
            raise ASTReject("schema constraints must be array")
    elif kind == "CONST":
        if node_id != LITERAL_REGISTRY or set(body) != {"members"} or not isinstance(body["members"], dict) or not body["members"]:
            raise ASTReject("CONST body/registry violation")
        for symbol, member in body["members"].items():
            if not CONST_RE.fullmatch(symbol) or not isinstance(member, dict) or set(member) != {"type", "value"}:
                raise ASTReject("invalid literal registry member")
            typ, wire = member["type"], member["value"]
            if typ not in {"STRING", "INTEGER", "BOOLEAN", "NULL", "DECIMAL_STRING"}:
                raise ASTReject("invalid literal registry type")
            if typ == "STRING" and (not isinstance(wire, str) or not wire.isascii() or not re.fullmatch(r"[!-~]{1,256}", wire) or NODE_ID_RE.fullmatch(wire)):
                raise ASTReject("invalid/free literal string")
            if typ == "INTEGER":
                _safe_int(wire, "literal integer")
            if typ == "DECIMAL_STRING" and (not isinstance(wire, str) or not DECIMAL_RE.fullmatch(wire)):
                raise ASTReject("invalid decimal literal")
    elif kind == "ALGORITHM":
        if set(body) != {"parameters", "returns", "locals", "preconditions", "statements", "postconditions"}:
            raise ASTReject("ALGORITHM exact body keys")
        for name, typ in {**body["parameters"], **body["locals"]}.items():
            if not FIELD_RE.fullmatch(name) or name in {"$self", "$result"}:
                raise ASTReject("invalid algorithm binding")
            _check_type_expr(typ, registry, algorithm_context=True)
        _check_type_expr(body["returns"], registry, algorithm_context=True)
        if node_id in SELECTOR_RETURNS and body["returns"] != SELECTOR_RETURNS[node_id]:
            raise ASTReject("selector result union must be profile-exact")
        if node_id == "algorithm/ValidateDecimal.v0.2.2":
            expected_kind = ["T_ENUM", [["CONST_REF", LITERAL_REGISTRY, DECIMAL_KIND_SYMBOLS[kind]] for kind in ("BPS", "DECIMAL", "MONEY", "PRICE", "QTY_BASE")]]
            if body["parameters"] != {"kind": expected_kind, "value": ["T_PRIMITIVE", "STRING"]} or body["returns"] != ["T_PRIMITIVE", "BOOLEAN"] or body["locals"] != {} or body["preconditions"] != [] or body["postconditions"] != []:
                raise ASTReject("ValidateDecimal signature must be profile-exact")
        if not all(isinstance(body[key], list) for key in ("preconditions", "statements", "postconditions")):
            raise ASTReject("algorithm arrays required")
    elif kind == "IDENTITY":
        if set(body) != {"domain_ascii", "parameters", "preimage", "output_type"} or not isinstance(body["domain_ascii"], str) or not body["domain_ascii"].isascii() or not body["domain_ascii"]:
            raise ASTReject("IDENTITY exact body")
        for name, typ in body["parameters"].items():
            if not FIELD_RE.fullmatch(name):
                raise ASTReject("invalid identity parameter")
            _check_type_expr(typ, registry)
        _check_type_expr(body["output_type"], registry)
    elif kind == "ROUTING":
        if set(body) != {"input_type", "discriminator", "discriminator_type", "value_path", "cases"}:
            raise ASTReject("ROUTING exact body keys")
        _check_type_expr(body["input_type"], registry)
        _check_type_expr(body["discriminator_type"], registry)
        if not isinstance(body["discriminator"], list) or not body["discriminator"]:
            raise ASTReject("routing discriminator must be nonempty path")
        if not isinstance(body["value_path"], list) or not isinstance(body["cases"], list) or not body["cases"]:
            raise ASTReject("routing path/cases")
        for case in body["cases"]:
            if not isinstance(case, dict) or set(case) != {"match", "schema_node_id"} or not isinstance(case["schema_node_id"], str) or not case["schema_node_id"].startswith("schema/"):
                raise ASTReject("routing case")
            _const_ref(case["match"], registry)


def validate_slice_a(nodes: dict[str, dict[str, Any]], expected_node_ids: set[str]) -> dict[str, dict[str, Any]]:
    if set(nodes) != expected_node_ids:
        missing, extra = expected_node_ids - set(nodes), set(nodes) - expected_node_ids
        raise ASTReject(f"Slice A key set mismatch missing={sorted(missing)} extra={sorted(extra)}")
    registry_envelope = nodes.get(LITERAL_REGISTRY)
    if not registry_envelope or registry_envelope.get("node_kind") != "CONST":
        raise ASTReject("literal registry missing")
    registry = registry_envelope.get("body", {}).get("members", {})
    observed: dict[str, dict[str, Any]] = {}
    for node_id in sorted(nodes):
        envelope = nodes[node_id]
        if not NODE_ID_RE.fullmatch(node_id) or not isinstance(envelope, dict) or set(envelope) != {"node_version", "node_id", "node_kind", "requires", "body"}:
            raise ASTReject("invalid NodeEnvelope")
        prefix = node_id.split("/", 1)[0]
        if envelope["node_version"] != NODE_VERSION or envelope["node_id"] != node_id or envelope["node_kind"] != KIND_BY_PREFIX[prefix]:
            raise ASTReject("NodeEnvelope prefix/kind/version mismatch")
        _check_body(node_id, envelope["node_kind"], envelope["body"], registry)
        refs: set[str] = set()
        _node_refs(envelope["body"], refs)
        requires = envelope["requires"]
        if not isinstance(requires, list) or requires != sorted(set(requires)) or set(requires) != refs:
            raise ASTReject("requires must equal sorted body reference set")
        for ref in refs:
            if not NODE_ID_RE.fullmatch(ref):
                raise ASTReject("invalid body NodeId reference")
        observed[node_id] = {"node_digest": node_digest(node_id, envelope), "outbound_refs": sorted(refs)}
    return observed
