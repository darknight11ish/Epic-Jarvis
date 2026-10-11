"""test_structured.py - constrained tool calls, and the line they must not cross.

Half of these are ordinary shape tests. The other half exist because the
failure this module could cause is worse than the one it fixes: a schema that
silently reads as a permission. A well-formed send_email is still a send_email,
and the tests below assert that nothing in this module says otherwise.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jarvis_structured as ST


class Schemas(unittest.TestCase):

    def test_a_tool_schema_pins_the_tool_name(self):
        s = ST.schema_for_tool("read_file", {"path": "string"}, ["path"])
        self.assertEqual(s["properties"]["tool"]["const"], "read_file")
        self.assertEqual(s["properties"]["arguments"]["required"], ["path"])

    def test_a_choice_schema_only_admits_tools_that_exist(self):
        """The other common failure: a confident call to a tool that is not
        there. An enum removes it rather than handling it."""
        s = ST.schema_for_choice([("read_file", {"path": "string"}, ["path"]),
                                  ("send_email", {"to": "string"}, ["to"])])
        self.assertEqual(s["properties"]["tool"]["enum"], ["read_file", "send_email"])
        self.assertEqual(ST.validate({"tool": "rm_rf", "arguments": {}}, s),
                         ["$.tool: must be one of ['read_file', 'send_email'], "
                          "got 'rm_rf'"])

    def test_an_unknown_type_is_left_alone_rather_than_guessed_at(self):
        s = ST.schema_for_tool("t", {"thing": "widget"})
        self.assertEqual(s["properties"]["arguments"]["properties"]["thing"]["type"],
                         "string")

    def test_a_nested_spec_is_passed_through(self):
        spec = {"type": "array", "items": {"type": "string"}}
        s = ST.schema_for_tool("t", {"paths": spec})
        self.assertEqual(s["properties"]["arguments"]["properties"]["paths"], spec)


class RequestBody(unittest.TestCase):

    def test_the_schema_goes_in_format(self):
        s = ST.schema_for_tool("read_file", {"path": "string"})
        body = ST.ollama_body("qwen3:8b", "do it", s)
        self.assertEqual(body["format"], s)
        self.assertFalse(body["stream"])

    def test_no_schema_means_no_format_field_at_all(self):
        """Not format="json". Sending the loose mode when the caller asked for
        nothing would quietly change what the model is allowed to say."""
        self.assertNotIn("format", ST.ollama_body("m", "p"))

    def test_the_body_is_json_serialisable(self):
        json.dumps(ST.ollama_body("m", "p", ST.FACTS_SCHEMA))


class Validation(unittest.TestCase):

    def setUp(self):
        self.s = ST.schema_for_tool("read_file", {"path": "string",
                                                  "lines": "integer"}, ["path"])

    def test_a_matching_call_has_no_problems(self):
        self.assertEqual(
            ST.validate({"tool": "read_file", "arguments": {"path": "/x"}}, self.s), [])

    def test_a_missing_required_argument_is_named(self):
        p = ST.validate({"tool": "read_file", "arguments": {}}, self.s)
        self.assertEqual(p, ["$.arguments.path: missing"])

    def test_the_wrong_tool_is_caught(self):
        p = ST.validate({"tool": "send_email", "arguments": {"path": "/x"}}, self.s)
        self.assertIn("must be 'read_file'", p[0])

    def test_a_wrong_type_names_the_path_and_both_types(self):
        p = ST.validate({"tool": "read_file",
                         "arguments": {"path": "/x", "lines": "ten"}}, self.s)
        self.assertEqual(p, ["$.arguments.lines: expected integer, got str"])

    def test_a_boolean_is_not_an_integer(self):
        """bool subclasses int in Python, so an isinstance check passes and the
        value behaves strangely three layers later."""
        p = ST.validate({"tool": "read_file",
                         "arguments": {"path": "/x", "lines": True}}, self.s)
        self.assertIn("got boolean", p[0])

    def test_array_items_are_checked_by_index(self):
        s = {"type": "array", "items": {"type": "string"}}
        self.assertEqual(ST.validate(["a", 2, "c"], s),
                         ["$[1]: expected string, got int"])

    def test_an_unlisted_property_is_not_an_error(self):
        """A model that volunteers an extra field has not done damage, and
        failing the turn for it produces a retry that says the same thing."""
        self.assertEqual(
            ST.validate({"tool": "read_file",
                         "arguments": {"path": "/x", "why": "because"}}, self.s), [])

    def test_the_facts_schema_rejects_the_empty_object_that_format_json_allows(self):
        """The reason this module exists. `{}` is valid JSON."""
        self.assertTrue(ST.validate({}, ST.FACTS_SCHEMA))
        self.assertEqual(ST.validate({"facts": []}, ST.FACTS_SCHEMA), [])

    def test_the_facts_schema_rejects_a_string_where_the_list_goes(self):
        self.assertTrue(ST.validate({"facts": "lots of them"}, ST.FACTS_SCHEMA))

    def test_a_fact_without_text_is_caught(self):
        self.assertTrue(ST.validate({"facts": [{"confidence": 0.9}]},
                                    ST.FACTS_SCHEMA))


class Parsing(unittest.TestCase):

    def test_a_code_fence_is_stripped(self):
        """A model that wraps its JSON in a fence has not misbehaved in any way
        worth failing a turn over, and refusing produces a retry that returns
        the same thing."""
        out = ST.parse('```json\n{"facts": []}\n```', ST.FACTS_SCHEMA)
        self.assertEqual(out, {"facts": []})

    def test_text_that_is_not_json_raises_with_the_reason(self):
        with self.assertRaises(ST.Invalid) as e:
            ST.parse("I'm sorry, I can't do that")
        self.assertIn("not JSON", str(e.exception))

    def test_a_bare_list_is_refused(self):
        with self.assertRaises(ST.Invalid):
            ST.parse("[1, 2, 3]")

    def test_a_schema_mismatch_raises_with_the_first_problems(self):
        s = ST.schema_for_tool("read_file", {"path": "string"}, ["path"])
        with self.assertRaises(ST.Invalid) as e:
            ST.parse('{"tool": "read_file", "arguments": {}}', s)
        self.assertIn("path: missing", str(e.exception))


class NotAPermission(unittest.TestCase):
    """The line this module must not cross."""

    def test_a_parsed_tool_call_says_it_has_not_been_gated(self):
        s = ST.schema_for_tool("send_email", {"to": "string"}, ["to"])
        out = ST.tool_call('{"tool":"send_email","arguments":{"to":"a@b.test"}}', s)
        self.assertTrue(out["valid_shape"])
        self.assertFalse(out["gated"])
        self.assertIn("jarvis_gate", out["note"])

    def test_a_perfectly_formed_destructive_call_is_still_just_a_shape(self):
        s = ST.schema_for_tool("run_shell", {"command": "string"}, ["command"])
        out = ST.tool_call('{"tool":"run_shell","arguments":{"command":"rm -rf /"}}', s)
        self.assertTrue(out["valid_shape"])
        self.assertFalse(out["gated"])

    def test_this_module_exposes_nothing_that_could_be_mistaken_for_approval(self):
        """Structural, like the arbiter's. The failure mode is somebody later
        reading `validate()` as a safety check and skipping the gate."""
        names = [n for n in dir(ST) if not n.startswith("_")]
        for banned in ("allow", "approve", "authorise", "authorize",
                       "permit", "check", "is_safe", "gate"):
            self.assertNotIn(banned, names)

    def test_the_module_says_so_in_its_own_status(self):
        self.assertIn("never authorises", ST.status()["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
