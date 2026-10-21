"""Orchestrate a full probe run against one MCP server."""
from __future__ import annotations

import time
from typing import Any, Optional

from .client import StdioMCPClient
from .errors import MCPError
from .synthesize import synthesize_arguments

STATUS_OK = "ok"                 # tool answered, isError=false
STATUS_TOOL_ERROR = "tool-error" # tool answered, isError=true (handled failure)
STATUS_TIMEOUT = "timeout"
STATUS_RPC_ERROR = "rpc-error"
STATUS_UNREACHABLE = "unreachable"  # server died / protocol broke


def _result_excerpt(result: dict[str, Any], limit: int = 200) -> str:
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    excerpt = " ".join(parts).strip() or "(no text content returned)"
    return excerpt[:limit]


def probe_server(command: list[str],
                 list_only: bool = False,
                 include_safe_calls: bool = True,
                 tool_filter: Optional[set[str]] = None,
                 call_timeout: float = 30.0,
                 connect_timeout: float = 20.0,
                 cwd: Optional[str] = None) -> dict[str, Any]:
    """Probe one MCP stdio server and return a structured report dict."""
    report: dict[str, Any] = {
        "serverCommand": command,
        "ok": False,
        "fatalError": None,
        "serverInfo": {},
        "protocolVersion": None,
        "toolCount": 0,
        "tools": [],
    }
    client: Optional[StdioMCPClient] = None
    try:
        client = StdioMCPClient(command, cwd=cwd, timeout=connect_timeout)
        info = client.initialize()
        report["serverInfo"] = info
        report["protocolVersion"] = client.protocol_version
        tools = client.list_tools()
        report["toolCount"] = len(tools)

        wanted = tools
        if tool_filter:
            wanted = [t for t in tools if t.get("name") in tool_filter]
            missing = tool_filter - {t.get("name") for t in tools}
            if missing:
                report["fatalError"] = (
                    f"tool(s) not advertised: {', '.join(sorted(missing))}")

        entries = []
        if list_only:
            for tool in tools:
                entries.append({
                    "name": tool.get("name"),
                    "description": (tool.get("description") or "")[:120],
                    "required": (tool.get("inputSchema") or {}).get(
                        "required", []),
                    "status": "listed",
                    "durationMs": None,
                    "output": None,
                })
        else:
            for tool in wanted:
                name = tool["name"]
                arguments = synthesize_arguments(
                    tool.get("inputSchema")) if include_safe_calls else {}
                entry = {
                    "name": name,
                    "description": (tool.get("description") or "")[:120],
                    "required": (tool.get("inputSchema") or {}).get(
                        "required", []),
                    "synthesizedArguments": arguments,
                    "status": None,
                    "durationMs": None,
                    "output": None,
                }
                started = time.monotonic()
                try:
                    result = client.call_tool(name, arguments,
                                              timeout=call_timeout)
                    entry["durationMs"] = round(
                        (time.monotonic() - started) * 1000, 1)
                    if result.get("isError"):
                        entry["status"] = STATUS_TOOL_ERROR
                        entry["output"] = _result_excerpt(result)
                    else:
                        entry["status"] = STATUS_OK
                        entry["output"] = _result_excerpt(result)
                except MCPError as exc:
                    entry["durationMs"] = round(
                        (time.monotonic() - started) * 1000, 1)
                    entry["status"] = STATUS_RPC_ERROR
                    entry["output"] = str(exc)
                except Exception as exc:  # noqa: BLE001 - probe must survive
                    entry["durationMs"] = round(
                        (time.monotonic() - started) * 1000, 1)
                    entry["status"] = STATUS_UNREACHABLE
                    entry["output"] = f"client-side exception: {exc!r}"
                entries.append(entry)
        report["tools"] = entries
        if report["fatalError"] is None:
            report["ok"] = True
    except MCPError as exc:
        report["fatalError"] = str(exc)
        if client is not None:
            report["stderrTail"] = client.stderr_tail
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # pragma: no cover
                pass
    return report


def probe_exit_code(report: dict[str, Any], fail_on_tool_error: bool) -> int:
    """Exit-code policy: 0 clean, 1 tool-level failures, 2 fatal failures."""
    if not report["ok"]:
        return 2
    bad = {"timeout": "timeout", "rpc-error": "rpc-error",
           "unreachable": "unreachable"}
    statuses = {tool["status"] for tool in report["tools"]}
    if statuses & set(bad):
        return 1
    if fail_on_tool_error and STATUS_TOOL_ERROR in statuses:
        return 1
    return 0
