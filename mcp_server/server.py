"""MCP server core: JSON-RPC 2.0 dispatch over the bounded read-only tool surface.

Implements the MCP lifecycle a client needs (`initialize`, `notifications/
initialized`, `ping`, `tools/list`, `tools/call`) with deliberately no
resources, prompts, sampling or write capabilities. Tool failures are returned
as in-band tool results (`isError: true`) so an agent can reason about them,
while protocol-level problems use standard JSON-RPC error codes.
"""

from __future__ import annotations

import json
import sys
import traceback

from . import MCP_SERVER_NAME, MCP_SERVER_VERSION, MCP_TOOLS_VERSION, contract
from .api_client import ReadOnlyViolation, UpstreamError
from .tools import HANDLERS, ToolInputError

JSONRPC_VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

MAX_INBOUND_MESSAGE_BYTES = 262_144
MAX_TOOL_RESULT_BYTES = 1_000_000

INSTRUCTIONS = (
    "Read-only price-intelligence tools for North Macedonia grocery retail. "
    "Prices, unit/pack conversions and basket totals are computed deterministically by the "
    "authoritative PostgreSQL/Java services; never recompute, round or estimate them. "
    "Always surface provenance (sourceUrl, publishedTs, fetchedTs) and never present a "
    "substitution candidate as an identical product. If a tool reports isError, state the "
    "limitation instead of inventing prices."
)


def error_response(request_id, code: int, message: str, data: dict | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def result_response(request_id, result: dict) -> dict:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _tool_success(payload: dict) -> dict:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text.encode("utf-8")) > MAX_TOOL_RESULT_BYTES:
        return _tool_error(
            {
                "reason": "result_too_large",
                "message": "tool result exceeded the bounded response size; narrow the request",
            }
        )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
    }


def _tool_error(info: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps({"error": info}, ensure_ascii=False, indent=2)}],
        "structuredContent": {"error": info},
        "isError": True,
    }


class McpServer:
    """Transport-agnostic MCP server; `handle_message` is pure (returns a dict)."""

    def __init__(self, client):
        self.client = client

    def _initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        version = (
            requested if requested in contract.MCP_PROTOCOL_VERSIONS else contract.DEFAULT_PROTOCOL_VERSION
        )
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }

    def handle_message(self, message):
        if not isinstance(message, dict):
            return error_response(None, INVALID_REQUEST, "JSON-RPC message must be an object")
        request_id = message.get("id")
        if message.get("jsonrpc") != JSONRPC_VERSION:
            return error_response(request_id, INVALID_REQUEST, 'jsonrpc must be "2.0"')
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return error_response(request_id, INVALID_REQUEST, "method must be a non-empty string")

        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return error_response(request_id, INVALID_PARAMS, "params must be an object")

        is_notification = "id" not in message or request_id is None

        if method == "initialize":
            if is_notification:
                return None
            return result_response(request_id, self._initialize(params))

        if is_notification:
            # notifications/initialized, notifications/cancelled and unknown
            # notifications never produce a JSON-RPC response.
            return None

        if method == "ping":
            return result_response(request_id, {})

        if method == "tools/list":
            return result_response(
                request_id,
                {"tools": contract.TOOLS, "_meta": {"toolsVersion": MCP_TOOLS_VERSION}},
            )

        if method == "tools/call":
            return self._call_tool(request_id, params)

        return error_response(request_id, METHOD_NOT_FOUND, f"method not supported: {method}")

    def _call_tool(self, request_id, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or name not in HANDLERS:
            return error_response(
                request_id,
                INVALID_PARAMS,
                f"unknown tool: {name!r}",
                {"availableTools": list(HANDLERS)},
            )
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return error_response(request_id, INVALID_PARAMS, "arguments must be an object")

        try:
            payload = HANDLERS[name](self.client, arguments)
        except ToolInputError as exc:
            return result_response(request_id, _tool_error(exc.as_dict()))
        except UpstreamError as exc:
            return result_response(request_id, _tool_error(exc.as_dict()))
        except ReadOnlyViolation as exc:
            return result_response(
                request_id,
                _tool_error({"reason": "read_only_violation", "message": str(exc)}),
            )
        except Exception:  # pragma: no cover - defensive
            traceback.print_exc(file=sys.stderr)
            return result_response(
                request_id,
                _tool_error(
                    {
                        "reason": "internal_error",
                        "message": "tool execution failed unexpectedly; no data was returned",
                    }
                ),
            )
        return result_response(request_id, _tool_success(payload))

    # -- newline-delimited transport (stdio) --------------------------------
    def handle_raw(self, raw: str):
        """Handle one newline-delimited JSON-RPC frame. Returns a JSON string or None."""
        if not isinstance(raw, str) or not raw.strip():
            return json.dumps(
                error_response(None, PARSE_ERROR, "empty JSON-RPC frame"), ensure_ascii=False
            )
        if len(raw.encode("utf-8")) > MAX_INBOUND_MESSAGE_BYTES:
            return json.dumps(
                error_response(None, INVALID_REQUEST, "JSON-RPC frame exceeds the inbound size limit"),
                ensure_ascii=False,
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps(error_response(None, PARSE_ERROR, "invalid JSON"), ensure_ascii=False)

        if isinstance(payload, list):
            if not payload:
                return json.dumps(
                    error_response(None, INVALID_REQUEST, "empty JSON-RPC batch"), ensure_ascii=False
                )
            responses = [
                resp for resp in (self.handle_message(item) for item in payload) if resp is not None
            ]
            if not responses:
                return None
            return json.dumps(responses, ensure_ascii=False)

        response = self.handle_message(payload)
        if response is None:
            return None
        return json.dumps(response, ensure_ascii=False)

