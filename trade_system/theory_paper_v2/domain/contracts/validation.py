"""Small deterministic validator for the materialized closed-schema subset."""

from __future__ import annotations

import re
from typing import Any, Mapping


class SchemaValidationError(ValueError):
    pass


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"SCHEMA_TYPE_UNSUPPORTED:{expected}")


def validate_schema_value(
    value: Any, schema: Mapping[str, Any], *, pointer: str = ""
) -> None:
    if "anyOf" in schema:
        failures = 0
        for candidate in schema["anyOf"]:
            try:
                validate_schema_value(value, candidate, pointer=pointer)
                return
            except SchemaValidationError:
                failures += 1
        raise SchemaValidationError(f"SCHEMA_ANY_OF_FAILED:{pointer}:{failures}")
    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"SCHEMA_CONST_MISMATCH:{pointer}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"SCHEMA_ENUM_UNKNOWN:{pointer}")
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise SchemaValidationError(f"SCHEMA_TYPE_MISMATCH:{pointer}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [field for field in required if field not in value]
        if missing:
            raise SchemaValidationError(
                f"SCHEMA_REQUIRED_MISSING:{pointer}:{','.join(missing)}"
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise SchemaValidationError(
                    f"SCHEMA_ADDITIONAL_PROPERTY:{pointer}:{','.join(extras)}"
                )
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                validate_schema_value(
                    child, child_schema, pointer=f"{pointer}/{key}"
                )
    elif isinstance(value, list):
        if schema.get("uniqueItems"):
            rendered = [repr(item) for item in value]
            if len(rendered) != len(set(rendered)):
                raise SchemaValidationError(f"SCHEMA_ARRAY_NOT_UNIQUE:{pointer}")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaValidationError(f"SCHEMA_ARRAY_TOO_SHORT:{pointer}")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, child in enumerate(value):
                validate_schema_value(
                    child, item_schema, pointer=f"{pointer}/{index}"
                )
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise SchemaValidationError(f"SCHEMA_STRING_TOO_SHORT:{pointer}")
        pattern = schema.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise SchemaValidationError(f"SCHEMA_PATTERN_MISMATCH:{pointer}")
    elif isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"SCHEMA_MINIMUM:{pointer}")

