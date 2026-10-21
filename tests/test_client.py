import sys
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mcp_probe.client import StdioMCPClient  # noqa: E402
from mcp_probe.errors import (MCPConnectionError, MCPError,  # noqa: E402
                              MCPProtocolError)

FAKE = [sys.executable, str(Path(__file__).parent / "fake_server.py")]


class TestClient(unittest.TestCase):
    def test_handshake_and_server_info(self):
        c = StdioMCPClient(FAKE)
        try:
            info = c.initialize()
            self.assertEqual(info["name"], "fake-mcp")
            self.assertEqual(info["version"], "0.9.0")
            self.assertEqual(c.protocol_version, "2025-06-18")
        finally:
            c.close()

    def test_list_tools_returns_all(self):
        c = StdioMCPClient(FAKE)
        try:
            c.initialize()
            tools = c.list_tools()
            names = [t["name"] for t in tools]
            self.assertEqual(names, ["echo", "add", "explode"])
        finally:
            c.close()

    def test_call_tool_happy_path(self):
        c = StdioMCPClient(FAKE)
        try:
            c.initialize()
            result = c.call_tool("echo", {"text": "hello"})
            self.assertFalse(result.get("isError", False))
            self.assertEqual(result["content"][0]["text"], "hello")
        finally:
            c.close()

    def test_call_tool_iserror_is_a_result_not_exception(self):
        c = StdioMCPClient(FAKE)
        try:
            c.initialize()
            result = c.call_tool("explode", {})
            self.assertTrue(result.get("isError"))
        finally:
            c.close()

    def test_unknown_tool_raises_protocol_error(self):
        c = StdioMCPClient(FAKE)
        try:
            c.initialize()
            with self.assertRaises(MCPProtocolError):
                c.call_tool("does_not_exist", {})
        finally:
            c.close()

    def test_missing_binary_raises_connection_error(self):
        with self.assertRaises(MCPError):
            StdioMCPClient(["definitely-not-a-real-binary-xyz-123"])

    def test_script_error_at_startup_raises_connection_error(self):
        c = StdioMCPClient([sys.executable, "/nonexistent/server.py"],
                           timeout=5)
        try:
            with self.assertRaises(MCPConnectionError):
                c.initialize()
        finally:
            c.close()

    def test_unresponsive_server_times_out(self):
        # A python that never speaks JSON: the CLI keeps its own entendido
        c = StdioMCPClient(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout=0.5)
        try:
            with self.assertRaises(MCPError):
                c.initialize()
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
