"""JSON-RPC 2.0 envelopes - port of McpProtocolModels.java (NON_NULL semantics)."""

from typing import Any


def mcp_response_success(identifier: Any, result: Any) -> dict[str, Any]:
    return _without_nulls({"jsonrpc": "2.0", "id": identifier, "result": result})


def mcp_response_error(identifier: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    return _without_nulls({
        "jsonrpc": "2.0",
        "id": identifier,
        "result": None,
        "error": _without_nulls({"code": code, "message": message, "data": data}),
    })


def _without_nulls(value):
    """Jackson @JsonInclude(NON_NULL) on McpResponse/McpError records."""
    if isinstance(value, dict):
        return {k: _without_nulls(v) for k, v in value.items() if v is not None}
    return value
