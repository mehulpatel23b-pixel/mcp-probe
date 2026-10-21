import sys
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mcp_probe.probe import probe_exit_code, probe_server  # noqa: E402

FAKE = [sys.executable, str(Path(__file__).parent / "fake_server.py")]


class TestProbe(unittest.TestCase):
    def test_full_probe(self):
        report = probe_server(FAKE, connect_timeout=10, call_timeout=10)
        self.assertTrue(report["ok"])
        self.assertEqual(report["toolCount"], 3)
        self.assertEqual(report["serverInfo"]["name"], "fake-mcp")
        by_name = {t["name"]: t for t in report["tools"]}
        self.assertEqual(by_name["echo"]["status"], "ok")
        self.assertEqual(by_name["add"]["status"], "ok")
        self.assertEqual(by_name["explode"]["status"], "tool-error")
        # synthesized arguments came from the schemas
        self.assertEqual(by_name["echo"]["synthesizedArguments"],
                         {"text": "mcp-probe"})
        self.assertEqual(by_name["add"]["synthesizedArguments"],
                         {"a": 0, "b": 0})
        # durations recorded for every probed tool
        self.assertTrue(all(t["durationMs"] is not None
                            for t in report["tools"]))

    def test_list_only_never_calls_tools(self):
        report = probe_server(FAKE, list_only=True, connect_timeout=10)
        self.assertTrue(report["ok"])
        for tool in report["tools"]:
            self.assertEqual(tool["status"], "listed")
            self.assertIsNone(tool["durationMs"])

    def test_tool_filter_probes_subset(self):
        report = probe_server(FAKE, tool_filter={"echo"},
                              connect_timeout=10, call_timeout=10)
        self.assertTrue(report["ok"])
        self.assertEqual(len(report["tools"]), 1)
        self.assertEqual(report["tools"][0]["name"], "echo")

    def test_missing_tool_is_fatal(self):
        report = probe_server(FAKE, tool_filter={"nope"},
                              connect_timeout=10, call_timeout=10)
        self.assertFalse(report["ok"])
        self.assertIn("not advertised", report["fatalError"])

    def test_broken_server_reports_fatal(self):
        report = probe_server(
            [sys.executable, "-c",
             "import sys; sys.stdout.write('this is not json\n');"
             " sys.stdout.flush(); import time; time.sleep(5)"],
            connect_timeout=10)
        self.assertFalse(report["ok"])
        self.assertTrue(report["fatalError"])

    def test_exit_code_policy(self):
        clean = probe_server(FAKE, connect_timeout=10, call_timeout=10)
        self.assertEqual(probe_exit_code(clean, False), 0)
        self.assertEqual(probe_exit_code(clean, True), 1)  # explode tool-errors
        broken = dict(clean, ok=False)
        self.assertEqual(probe_exit_code(broken, False), 2)
        empty = dict(clean, tools=[])
        self.assertEqual(probe_exit_code(empty, False), 0)


if __name__ == "__main__":
    unittest.main()
