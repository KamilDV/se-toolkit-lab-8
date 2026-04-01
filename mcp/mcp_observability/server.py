"""MCP server exposing VictoriaLogs and VictoriaTraces as tools."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

server = Server("observability")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_VLOGS_URL = os.environ.get("VICTORIALOGS_URL", "http://localhost:42010")
_VTRACES_URL = os.environ.get("VICTORIATRACES_URL", "http://localhost:42011")

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class _NoArgs(BaseModel):
    """Empty input model for tools that only need server-side configuration."""


class _LogsSearchQuery(BaseModel):
    query: str = Field(
        default="*",
        description="LogsQL query string (e.g., 'error', 'level:error', '_stream:{service=\"backend\"}')",
    )
    limit: int = Field(
        default=10, ge=1, le=100, description="Max log entries to return (default 10)"
    )


class _LogsErrorCountQuery(BaseModel):
    service: str = Field(
        default="*",
        description="Service name to filter (use '*' for all services)",
    )
    hours: int = Field(
        default=1, ge=1, le=24, description="Time window in hours (default 1)"
    )


class _TracesListQuery(BaseModel):
    service: str = Field(
        default="Learning Management Service",
        description="Service name to filter traces",
    )
    limit: int = Field(
        default=10, ge=1, le=50, description="Max traces to return (default 10)"
    )


class _TracesGetQuery(BaseModel):
    trace_id: str = Field(description="Trace ID to fetch")


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------


async def _vlogs_request(path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Make HTTP request to VictoriaLogs."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{_VLOGS_URL}{path}"
        response = await client.get(url, params=params)
        response.raise_for_status()
        # VictoriaLogs returns newline-delimited JSON
        lines = response.text.strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]


async def _vtraces_request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make HTTP request to VictoriaTraces (Jaeger API)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{_VTRACES_URL}{path}"
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _text(data: Any) -> list[TextContent]:
    """Serialize data to JSON text."""
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _logs_search(args: _LogsSearchQuery) -> list[TextContent]:
    """Search logs using VictoriaLogs."""
    try:
        results = await _vlogs_request(
            "/select/logsql/query",
            {"query": args.query, "limit": args.limit},
        )
        if not results:
            return _text({"message": "No logs found", "query": args.query})
        return _text({"logs": results, "count": len(results)})
    except httpx.HTTPError as e:
        return _text({"error": f"VictoriaLogs error: {e}"})


async def _logs_error_count(args: _LogsErrorCountQuery) -> list[TextContent]:
    """Count errors per service over a time window."""
    try:
        # Build query for errors
        if args.service == "*":
            query = "level:error OR severity:ERROR OR severity:error"
        else:
            query = f'_stream:{{service="{args.service}"}} AND (level:error OR severity:ERROR)'
        
        results = await _vlogs_request(
            "/select/logsql/query",
            {"query": query, "limit": 1000},
        )
        
        # Count by service
        error_count = len(results)
        by_service: dict[str, int] = {}
        for log in results:
            svc = log.get("service.name", log.get("service", "unknown"))
            by_service[svc] = by_service.get(svc, 0) + 1
        
        return _text({
            "total_errors": error_count,
            "time_window_hours": args.hours,
            "by_service": by_service,
        })
    except httpx.HTTPError as e:
        return _text({"error": f"VictoriaLogs error: {e}"})


async def _traces_list(args: _TracesListQuery) -> list[TextContent]:
    """List recent traces for a service."""
    try:
        # VictoriaTraces Jaeger API
        result = await _vtraces_request(
            "/jaeger/api/traces",
            {"service": args.service, "limit": args.limit},
        )
        traces = result.get("data", [])
        summary = []
        for trace in traces[: args.limit]:
            summary.append({
                "trace_id": trace.get("traceID"),
                "spans": len(trace.get("spans", [])),
                "start_time": trace.get("startTime"),
            })
        return _text({"traces": summary, "count": len(summary)})
    except httpx.HTTPError as e:
        return _text({"error": f"VictoriaTraces error: {e}"})


async def _traces_get(args: _TracesGetQuery) -> list[TextContent]:
    """Fetch a specific trace by ID."""
    try:
        result = await _vtraces_request(f"/jaeger/api/traces/{args.trace_id}")
        data = result.get("data", [])
        if not data:
            return _text({"error": f"Trace not found: {args.trace_id}"})
        trace = data[0]
        spans = trace.get("spans", [])
        span_summary = []
        for span in spans:
            span_summary.append({
                "span_id": span.get("spanID"),
                "operation": span.get("operationName"),
                "service": span.get("process", {}).get("serviceName"),
                "duration_ms": span.get("duration", 0) // 1000,
            })
        return _text({
            "trace_id": trace.get("traceID"),
            "spans": span_summary,
            "total_spans": len(spans),
        })
    except httpx.HTTPError as e:
        return _text({"error": f"VictoriaTraces error: {e}"})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_Registry = tuple[type[BaseModel], Callable[..., Awaitable[list[TextContent]]], Tool]

_TOOLS: dict[str, _Registry] = {}


def _register(
    name: str,
    description: str,
    model: type[BaseModel],
    handler: Callable[..., Awaitable[list[TextContent]]],
) -> None:
    schema = model.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)
    _TOOLS[name] = (model, handler, Tool(name=name, description=description, inputSchema=schema))


_register(
    "logs_search",
    "Search logs in VictoriaLogs using LogsQL. Returns matching log entries.",
    _LogsSearchQuery,
    _logs_search,
)
_register(
    "logs_error_count",
    "Count errors per service over a time window. Returns total count and breakdown by service.",
    _LogsErrorCountQuery,
    _logs_error_count,
)
_register(
    "traces_list",
    "List recent traces for a service from VictoriaTraces. Returns trace summaries.",
    _TracesListQuery,
    _traces_list,
)
_register(
    "traces_get",
    "Fetch a specific trace by ID from VictoriaTraces. Returns span hierarchy with timing.",
    _TracesGetQuery,
    _traces_get,
)


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [entry[2] for entry in _TOOLS.values()]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    entry = _TOOLS.get(name)
    if entry is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    model_cls, handler, _ = entry
    try:
        args = model_cls.model_validate(arguments or {})
        return await handler(args)
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {type(exc).__name__}: {exc}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
