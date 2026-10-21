"""Synthesize safe dummy arguments from a tool's JSON Schema.

mcp-probe calls every advertised tool once with minimal, harmless arguments
built from the schema's required properties. The goal is a smoke test ("does
the tool respond instead of crashing the server"), not a correctness test,
and most tools will legitimately reject the dummy values. That is expected.
"""
from __future__ import annotations

from typing import Any

STRATEGY_SENTINEL = "mcp-probe"


def _zero_value(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else None
    if schema_type == "string":
        return STRATEGY_SENTINEL
    if schema_type in ("integer", "number"):
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "array":
        return []
    if schema_type == "object":
        return {}
    if schema_type == "null":
        return None
    # Unknown / missing type: a harmless string default.
    return STRATEGY_SENTINEL


def synthesize_arguments(input_schema: Any) -> dict[str, Any]:
    """Build a minimal argument dict for the tool's required properties."""
    if not isinstance(input_schema, dict):
        return {}
    properties = input_schema.get("properties")
    required = input_schema.get("required")
    if not required:
        return {}
    arguments: dict[str, Any] = {}
    if not isinstance(properties, dict):
        properties = {}
    for prop_name in required:
        if isinstance(prop_name, str):
            arguments[prop_name] = _zero_value(properties.get(prop_name, {}))
    return arguments
