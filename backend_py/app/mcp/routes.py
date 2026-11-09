"""MCP JSON-RPC endpoint + server info + SSE - port of McpController.java."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.jsonx import RestJSONResponse
from app.mcp.protocol import mcp_response_error, mcp_response_success


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ai-shopping-mcp-server"
SERVER_VERSION = "0.5.0"


def make_mcp_router(registry) -> APIRouter:
    router = APIRouter(default_response_class=RestJSONResponse)

    @router.post("/mcp")
    async def handle_json_rpc(request: Request):
        body = await request.body()
        if not body:
            payload = None
        else:
            import json

            try:
                payload = json.loads(body)
            except Exception:
                # Malformed JSON -> Spring Boot default 400 whitelabel body.
                return SpringErrorResponse(request, 400, "Bad Request")
        if payload is None or not isinstance(payload, dict):
            return RestJSONResponse(
                status_code=400,
                content=mcp_response_error(None, -32600, "Invalid Request: missing method"),
            )
        id_value = payload.get("id")
        method = payload.get("method")
        if method is None:
            return RestJSONResponse(
                status_code=400,
                content=mcp_response_error(None, -32600, "Invalid Request: missing method"),
            )

        method = str(method).strip()
        params = payload.get("params") if isinstance(payload.get("params"), dict) else None

        if id_value is None and method.startswith("notifications/"):
            return Response(status_code=204)

        try:
            if method == "initialize":
                return RestJSONResponse(status_code=200, content=mcp_response_success(id_value, _initialize_result()))
            if method == "notifications/initialized":
                return Response(status_code=204)
            if method == "ping":
                return RestJSONResponse(status_code=200, content=mcp_response_success(id_value, {}))
            if method == "tools/list":
                return RestJSONResponse(
                    status_code=200,
                    content=mcp_response_success(id_value, {"tools": registry.list_tools()}),
                )
            if method == "tools/call":
                return RestJSONResponse(
                    status_code=200,
                    content=mcp_response_success(id_value, _handle_tool_call(registry, params)),
                )
            return RestJSONResponse(
                status_code=200,
                content=mcp_response_error(id_value, -32601, f"Method not found: {method}"),
            )
        except ValueError as exc:
            return RestJSONResponse(
                status_code=200,
                content=mcp_response_error(id_value, -32602, f"Invalid params: {str(exc) if str(exc) else exc}"),
            )
        except Exception as exc:
            message = str(exc) if str(exc) else repr(exc)
            return RestJSONResponse(
                status_code=200,
                content=mcp_response_error(id_value, -32603, f"Internal error: {message}"),
            )

    @router.get("/mcp")
    def server_info() -> dict[str, Any]:
        return {
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "protocolVersion": PROTOCOL_VERSION,
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "sseEndpoint": "/mcp/sse",
            "capabilities": {"tools": {"listChanged": False}},
        }

    @router.get("/mcp/sse", response_class=StreamingResponse)
    async def sse_endpoint():
        async def gen():
            yield "event:endpoint\ndata:/mcp\n\n"
            await asyncio.sleep(60)

        return StreamingResponse(gen(), media_type="text/event-stream", status_code=200)

    return router


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def _handle_tool_call(registry, params):
    if params is None or "name" not in params:
        raise ValueError("'name' is required for tools/call")
    tool_name = str(params.get("name"))
    raw_arguments = params.get("arguments")
    arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
    return registry.call_tool(tool_name, arguments)


def SpringErrorResponse(request: Request, status_code: int, error_text: str) -> Response:
    from app.jsonx import spring_error_body

    return RestJSONResponse(
        status_code=status_code,
        content=spring_error_body(status_code, error_text, request.url.path),
    )
