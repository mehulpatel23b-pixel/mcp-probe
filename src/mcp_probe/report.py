"""Render a probe report as human text or JSON."""
from __future__ import annotations

import json
from typing import Any

BADGES = {"ok": "[ok]", "tool-error": "[ERR]",
          "timeout": "[TMO]", "rpc-error": "[RPC]",
          "unreachable": "[DEAD]", "listed": "[lst]"}


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    cmd = " ".join(report["serverCommand"])
    lines.append(f"mcp-probe report")
    lines.append(f"  command     : {cmd}")
    info = report.get("serverInfo") or {}
    name = info.get("name", "?")
    version = info.get("version", "?")
    lines.append(f"  server      : {name} v{version}")
    lines.append(f"  protocol    : {report.get('protocolVersion') or '?'}")
    lines.append(f"  handshake   : {'OK' if report['ok'] else 'FAILED'}")
    lines.append(f"  tools found : {report['toolCount']}")
    if report.get("fatalError"):
        lines.append(f"  fatal error : {report['fatalError']}")
        if report.get("stderrTail"):
            lines.append(f"  server stderr (tail):")
            for chunk in report["stderrTail"].splitlines()[-10:]:
                lines.append(f"    | {chunk}")
    if report["tools"]:
        lines.append("")
        lines.append(f"  {'status':7} {'ms':>8}  tool")
        lines.append(f"  {'-'*7} {'-'*8}  {'-'*34}")
        for tool in report["tools"]:
            badge = BADGES.get(tool["status"], "[?]")
            duration = (f"{tool['durationMs']:.0f}"
                        if tool.get("durationMs") is not None else "-")
            req = ", ".join(tool.get("required") or []) or "-"
            lines.append(f"  {badge:7} {duration:>8}  {tool['name']}"
                         f"  (required: {req})")
            if tool.get("output"):
                first_line = str(tool["output"]).splitlines()[0][:80]
                lines.append(f"           output: {first_line}")
    lines.append("")
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    clean = dict(report)
    if "serverCommand" in clean and isinstance(clean["serverCommand"], list):
        clean["serverCommand"] = clean["serverCommand"]
    return json.dumps(clean, indent=2, sort_keys=False, default=str)
