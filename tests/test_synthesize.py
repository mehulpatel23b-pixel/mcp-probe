import sys
import unittest

sys.path.insert(0, "src")

from mcp_probe.synthesize import synthesize_arguments  # noqa: E402


class TestSynthesize(unittest.TestCase):
    def test_string_required(self):
        schema = {"type": "object",
                  "properties": {"text": {"type": "string"}},
                  "required": ["text"]}
        self.assertEqual(synthesize_arguments(schema), {"text": "mcp-probe"})

    def test_numbers_required(self):
        schema = {"type": "object",
                  "properties": {"a": {"type": "number"},
                                 "b": {"type": "integer"}},
                  "required": ["a", "b"]}
        self.assertEqual(synthesize_arguments(schema), {"a": 0, "b": 0})

    def test_no_required_means_no_args(self):
        schema = {"type": "object",
                  "properties": {"x": {"type": "string"}},
                  "required": []}
        self.assertEqual(synthesize_arguments(schema), {})

    def test_bad_schema_is_safe(self):
        self.assertEqual(synthesize_arguments(None), {})
        self.assertEqual(synthesize_arguments("nonsense"), {})

    def test_unknown_type_falls_back_to_string(self):
        schema = {"type": "object",
                  "properties": {"mystery": {"type": "future"}},
                  "required": ["mystery"]}
        self.assertEqual(synthesize_arguments(schema),
                         {"mystery": "mcp-probe"})

    def test_boolean_and_array_and_object(self):
        schema = {"type": "object",
                  "properties": {"flag": {"type": "boolean"},
                                 "list": {"type": "array"},
                                 "nested": {"type": "object"}},
                  "required": ["flag", "list", "nested"]}
        self.assertEqual(synthesize_arguments(schema),
                         {"flag": False, "list": [], "nested": {}})


if __name__ == "__main__":
    unittest.main()
