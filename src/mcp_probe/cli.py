"""Command-line entry point for mcp-probe."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import __version__
from .probe import probe_exit_code, probe_server
from .report import render_json, render_text

EPILOG = """examples:
  # probe a server the easy way (command after --)
  mcp-probe -- npx -y @modelcontextprotocol/server-filesystem /tmp

  # only list advertised tools
  mcp-probe --list-only -- uvx mcp-server-fetch

  # probe one specific tool, JSON output for CI
  mcp-probe --tool search --format json -- python my_server.py
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-probe",
        description=("Zero-dependency smoke-tester for MCP (Model Context "
                      "Protocol) stdio servers: handshake, tool listing, "
                      "and safe synthesized tool calls, with CI exit codes."),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version",
                        version=f"mcp-probe {__version__}")
    parser.add_argument("--list-only", action="store_true",
                        help="only list advertised tools, do not call them")
    parser.add_argument("--tool", action="append", default=None,
                        metavar="NAME", dest="tools",
                        help="probe only this tool (repeatable)")
    parser.add_argument("--no-calls", action="store_true",
                        help="handshake + list only, alias of --list-only")
    parser.add_argument("--fail-on-tool-error", action="store_true",
                        help="exit 1 when a tool answers with isError=true "
                             "(default: FATAL protocol failures exit 1, "
                             "handled tool errors only warn)")
    parser.add_argument("--format", choices=("text", "json"),
                        default="text", dest="output_format")
    parser.add_argument("--connect-timeout", type=float, default=20.0,
                        help="seconds to wait for handshake/list (default 20)")
    parser.add_argument("--call-timeout", type=float, default=30.0,
                        help="seconds to wait per tool call (default 30)")
    parser.add_argument("--cwd", default=None,
                        help="working directory for the server process")
    parser.add_argument("server_command", nargs=argparse.REMAINDER,
                        metavar="-- SERVER COMMAND...",
                        help="command (after --) that starts the MCP server")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if (len(argv) == 1 and " " in argv[0]
            and not argv[0].startswith("-")):
        # allow: mcp-probe "uvx mcp-server-fetch" as a single quoted string
        import shlex
        argv = shlex.split(argv[0])
    parser = build_parser()
    args = parser.parse_args(argv)
    command = list(args.server_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.print_usage(sys.stderr)
        print("error: provide the server command after '--'",
              file=sys.stderr)
        return 2

    report = probe_server(
        command,
        list_only=args.list_only or args.no_calls,
        tool_filter=set(args.tools) if args.tools else None,
        call_timeout=args.call_timeout,
        connect_timeout=args.connect_timeout,
        cwd=args.cwd,
    )
    if args.output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return probe_exit_code(report, args.fail_on_tool_error)


if __name__ == "__main__":
    raise SystemExit(main())
