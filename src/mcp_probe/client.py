"""Minimal MCP client over the stdio transport.

Implements just enough of the Model Context Protocol (JSON-RPC 2.0,
newline-delimited frames over the server's stdin/stdout) to initialize a
session, list tools, and call tools. Zero third-party dependencies.

Protocol reference: https://modelcontextprotocol.io
"""
from __future__ import annotations

import json
import select
import subprocess
import time
from typing import Any, Optional

from .errors import MCPConnectionError, MCPProtocolError, MCPTimeoutError

DEFAULT_TIMEOUT = 20.0


class StdioMCPClient:
    """Talk to an MCP server launched as a local subprocess."""

    def __init__(self, command: list[str], cwd: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:  # pragma: no cover - depends on host OS
            raise MCPConnectionError(
                f"failed to launch server {command!r}: {exc}") from exc
        self.command = command
        self.timeout = timeout
        self._next_id = 0
        self.server_info: dict[str, Any] = {}
        self.protocol_version: Optional[str] = None
        self.stderr_tail = ""

    # ------------------------------------------------------------------ wire

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(
                (json.dumps(payload, separators=(",", ":")) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPConnectionError(
                f"server closed stdin while we were writing: {exc}") from exc

    def _readline(self, timeout: float) -> str:
        assert self.proc.stdout is not None
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(
                    f"no response from server within {timeout:.1f}s")
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if ready:
                line = self.proc.stdout.readline()
                if not line:
                    self._drain_stderr()
                    raise MCPConnectionError(
                        "server exited before answering "
                        f"(code={self.proc.poll()}); stderr: {self.stderr_tail}")
                return line.decode("utf-8", "replace")

    def _request(self, method: str, params: Optional[dict[str, Any]] = None,
                 timeout: Optional[float] = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        frame: dict[str, Any] = {
            "jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            frame["params"] = params
        self._send(frame)

        effective_timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + effective_timeout
        while True:
            line = self._readline(max(0.05, deadline - time.monotonic()))
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MCPProtocolError(
                    f"server sent non-JSON line: {line[:200]!r}") from exc
            if message.get("id") != request_id:
                continue  # notification, server-initiated request, or stale
            if "error" in message and message["error"] is not None:
                err = message["error"]
                raise MCPProtocolError(
                    f"{method} failed: [{err.get('code')}] {err.get('message')}")
            if "result" not in message:
                raise MCPProtocolError(
                    f"{method}: response has no result and no error")
            return message["result"]

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _drain_stderr(self) -> None:
        try:
            assert self.proc.stderr is not None
            self.stderr_tail = (self.proc.stderr.read() or b"")
            if isinstance(self.stderr_tail, bytes):
                self.stderr_tail = self.stderr_tail.decode("utf-8", "replace")
            self.stderr_tail = self.stderr_tail[-2000:]
        except Exception:  # pragma: no cover
            self.stderr_tail = ""

    # ------------------------------------------------------------ protocol

    def initialize(self, client_name: str = "mcp-probe",
                   client_version: str = "1.0.0",
                   protocol_version: str = "2025-06-18") -> dict[str, Any]:
        """Run the MCP initialize handshake and return serverInfo."""
        if self.server_info:
            return self.server_info
        result = self._request("initialize", {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version},
        })
        self.protocol_version = result.get("protocolVersion", protocol_version)
        self.server_info = result.get("serverInfo") or {}
        if not self.server_info:
            raise MCPProtocolError(
                "initialize succeeded but serverInfo is missing")
        self._notify("notifications/initialized")
        return self.server_info

    def list_tools(self, timeout: Optional[float] = None) -> list[dict[str, Any]]:
        """Return every advertised tool, following pagination cursors."""
        tools: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            result = self._request("tools/list", params or None, timeout)
            batch = result.get("tools") or []
            if not isinstance(batch, list):
                raise MCPProtocolError("tools/list: 'tools' is not a list")
            saw = {t.get("name") for t in tools}
            for tool in batch:
                if not isinstance(tool.get("name"), str) or not tool["name"]:
                    raise MCPProtocolError("tool entry without a valid name")
                if tool["name"] not in saw:
                    tools.append(tool)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None,
                  timeout: Optional[float] = None) -> dict[str, Any]:
        """Invoke a tool and return the raw MCP result object."""
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        result = self._request("tools/call", params, timeout)
        if not isinstance(result, dict):
            raise MCPProtocolError(
                f"tools/call({name}): result is not an object")
        return result

    # ------------------------------------------------------- lifecycle

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    self.proc.kill()
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
