#!/usr/bin/env python3
"""Minimal MCP-like stdio server used as a test fixture.

Speaks newline-delimited JSON-RPC 2.0: initialize, tools/list, tools/call.
Tool "explode" always returns isError=true. Comments stay off the wire.
"""
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "explode",
        "description": "Always fails with isError=true (tests soft-failure).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def respond(request_id, result):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
    sys.stdout.flush()


def fail(request_id, code, message):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": request_id,
         "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:  # notification
            continue
        method = msg.get("method")
        if method == "initialize":
            respond(msg["id"], {
                "protocolVersion": msg["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "0.9.0"},
            })
        elif method == "tools/list":
            respond(msg["id"], {"tools": TOOLS})
        elif method == "tools/call":
            name = msg["params"]["name"]
            args = msg["params"].get("arguments") or {}
            if name == "echo":
                respond(msg["id"], {"content": [
                    {"type": "text", "text": args.get("text", "")}]})
            elif name == "add":
                total = args.get("a", 0) + args.get("b", 0)
                respond(msg["id"], {"content": [
                    {"type": "text", "text": str(total)}]})
            elif name == "explode":
                respond(msg["id"], {
                    "isError": True,
                    "content": [{"type": "text", "text": "kaboom: bad input"}],
                })
            else:
                fail(msg["id"], -32601, f"unknown tool: {name}")
        else:
            fail(msg["id"], -32601, f"unknown method: {method}")


if __name__ == "__main__":
    main()
