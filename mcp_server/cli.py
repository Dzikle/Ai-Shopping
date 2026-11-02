"""stdio entry point for the read-only AI Shopping MCP server (M5).

Usage (any MCP client, e.g. an agent host):

    AI_SHOPPING_API_BASE=http://localhost:8080 python -B -m mcp_server.cli

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport).
All diagnostics go to stderr so stdout stays a clean protocol stream.

The server never opens a database connection and never talks to a retailer: it
only calls the allowlisted read-only REST endpoints of the M3/M4 backend.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_server import MCP_SERVER_NAME, MCP_SERVER_VERSION, MCP_TOOLS_VERSION, contract  # noqa: E402
from mcp_server.api_client import (  # noqa: E402
    ALLOWED_ROUTE_DESCRIPTIONS,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    CatalogApiClient,
)
from mcp_server.server import McpServer  # noqa: E402

DEFAULT_API_BASE = "http://localhost:8080"


def _reconfigure(stream, **kwargs) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(**kwargs)
    except (ValueError, OSError):  # pragma: no cover - platform dependent
        pass


def serve(server: McpServer, stdin, stdout) -> int:
    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        response = server.handle_raw(line)
        if response is None:
            continue
        stdout.write(response + "\n")
        stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp_server.cli",
        description=(
            f"{MCP_SERVER_NAME} {MCP_SERVER_VERSION} — bounded read-only MCP server "
            f"(tools {MCP_TOOLS_VERSION})"
        ),
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("AI_SHOPPING_API_BASE", DEFAULT_API_BASE),
        help="Base URL of the M3/M4 Spring Boot REST API (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("AI_SHOPPING_API_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        help="Read timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=int(os.environ.get("AI_SHOPPING_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES)),
        help="Hard cap for an upstream JSON response (default: %(default)s)",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the versioned tool contract as JSON and exit (no API calls).",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_tools:
        json.dump(
            {
                "server": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
                "toolsVersion": MCP_TOOLS_VERSION,
                "allowedRoutes": list(ALLOWED_ROUTE_DESCRIPTIONS),
                "tools": contract.TOOLS,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    client = CatalogApiClient(
        args.api_base,
        timeout=args.timeout,
        max_response_bytes=args.max_response_bytes,
    )
    server = McpServer(client)

    _reconfigure(sys.stdin, encoding="utf-8", errors="replace", newline="\n")
    _reconfigure(sys.stdout, encoding="utf-8", newline="\n")
    print(
        f"{MCP_SERVER_NAME} {MCP_SERVER_VERSION}: stdio ready, upstream={client.base_url}, "
        f"tools={len(contract.TOOLS)}, mode=read-only",
        file=sys.stderr,
        flush=True,
    )
    try:
        return serve(server, sys.stdin, sys.stdout)
    except KeyboardInterrupt:  # pragma: no cover - interactive convenience
        return 0
    except BrokenPipeError:  # pragma: no cover - client went away
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
