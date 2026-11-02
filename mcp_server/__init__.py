"""Bounded, strictly read-only MCP (Model Context Protocol) tool layer (M5).

The package exposes the deterministic M3/M4 Spring Boot REST API to AI agents as
a small, allowlisted set of MCP tools. It never writes to the catalog, never
performs price/unit/basket arithmetic itself, and never hides provenance:
prices, pack counts, totals and savings are always the exact values computed by
PostgreSQL/Java and returned by the REST API (ADR-0001, ADR-0002, ADR-0004).
"""

MCP_SERVER_NAME = "ai-shopping-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_TOOLS_VERSION = "v1"

__all__ = ["MCP_SERVER_NAME", "MCP_SERVER_VERSION", "MCP_TOOLS_VERSION"]
