"""jarvis_tool_schema.py: the schema a `format` field may carry, and the guard
that keeps a tool schema inside what `check_call` actually validates.

WHAT IS PROVEN HERE, each against a dict and nothing else - no network, no model,
no Ollama, and every socket refused for the whole run:

  * the keywords the live grammar was measured NOT to express (allOf, not,
    if/then/else, and any `format` other than date/date-time/time/uuid) are
    REFUSED by default, so a constraint cannot silently no-op;
  * a schema that uses only expressed keywords is passed through UNCHANGED -
    the control that stops a refuser which refuses everything from looking right;
  * `flatten` mode merges `allOf` upward for real (the merged schema enforces
    what the members said) and reports everything it removed;
  * the guard FAILS on a tool schema using a keyword `_schema_problems()` does
    not read, and PASSES on the real `jarvis_agent.TOOLS` - which is the fact
    that says item 3 of the work item was already built;
  * nothing here approves, writes, sends or reaches anything.

    python3 test_tool_schema.py
"""
import ast
import os
import socket
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO  # noqa: E402,F401  (puts BACKEND on sys.path)
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.append(str(REPO / "jarvis-backend"))

import jarvis_tool_schema as T  # noqa: E402


# Counting only: nothing in this module may open a connection.
#
# A CLASS, not a function, and that is load-bearing: `ssl.py` does
# `class SSLSocket(socket)` at import time (Lib/ssl.py:943), so replacing
# `socket.socket` with a plain function makes importing `http.client` - and so
# `jarvis_agent` - fail with "function() argument 'code' must be code, not str".
# Measured here: the first version of this guard SKIPPED the one check that
# reads the real 31 tool schemas, and a skip is not a pass. A class can be
# subclassed, so `ssl` imports, and instantiating it still raises.
class _NoNetworkSocket:
    def __init__(self, *a, **k):
        raise AssertionError("jarvis_tool_schema opened a network connection")


def _no_network(*a, **k):
    raise AssertionError("jarvis_tool_schema opened a network connection")


socket.socket = _NoNetworkSocket
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))
    return bool(cond)


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


PLAIN = {"type": "object", "properties": {"a": {"type": "string"}},
         "required": ["a"]}


# --------------------------------------------------------------------------
#   What the grammar expresses
# --------------------------------------------------------------------------

def t_a_schema_using_only_expressed_keywords_passes_through_unchanged():
    """THE CONTROL. A refuser that refused everything would pass every other
    test in this file; this one is what stops that."""
    out = T.sanitise_schema(PLAIN)
    check("it is accepted", out["ok"] is True and out["refused"] is False, repr(out))
    check("and it is UNCHANGED, byte for byte",
          out["schema"] == PLAIN and out["schema"] is not PLAIN, repr(out["schema"]))
    check("nothing is reported as removed", out["removed"] == [], repr(out["removed"]))
    # Every measured-expressed keyword, on its own, still passes.
    for kw, value in (("enum", ["x"]), ("const", "x"), ("oneOf", [{"type": "string"}]),
                      ("anyOf", [{"type": "string"}]), ("$ref", "#/$defs/S"),
                      ("$defs", {"S": {"type": "string"}}),
                      ("definitions", {"S": {"type": "string"}}),
                      ("pattern", "^[a-z]+$"), ("patternProperties", {}),
                      ("additionalProperties", False), ("minimum", 1),
                      ("maximum", 9), ("minLength", 1), ("maxLength", 9),
                      ("maxItems", 3), ("items", {"type": "string"}),
                      ("description", "d"), ("title", "t"), ("default", "z")):
        s = {"type": "object", "properties": {"a": value if kw in
             ("oneOf", "anyOf", "enum", "const", "pattern", "patternProperties",
              "additionalProperties", "minimum", "maximum", "minLength",
              "maxLength", "maxItems", "items", "$ref", "description",
              "title", "default") else {"type": "string"}}}
        if kw in ("$defs", "definitions"):
            s[kw] = value
            s["properties"] = {"a": {"$ref": f"#/{kw}/S"}}
        r = T.sanitise_schema(s)
        check(f"{kw!r} is expressed, so it passes", r["ok"] is True, repr(r)[:180])


def t_the_four_unexpressed_keywords_are_refused_by_default():
    for label, schema in (
            ("allOf", {"type": "object", "properties": {"a": {"allOf": [{"type": "integer"}]}}}),
            ("not", {"type": "object", "properties": {"a": {"not": {"type": "string"}}}}),
            ("if/then/else", {"type": "object", "if": {"properties": {}},
                              "then": {"required": ["b"]}, "else": {"required": ["c"]}}),
            ("format: email", {"type": "object",
                               "properties": {"a": {"type": "string", "format": "email"}}})):
        out = T.sanitise_schema(schema)
        check(f"{label} is refused", out["ok"] is False and out["refused"] is True,
              repr(out)[:200])
        check(f"{label} says why the grammar cannot express it",
              "not express" in out["reason"] or "ignores it" in out["reason"],
              out["reason"])
        check(f"{label} sends nothing at all", out["schema"] is None, repr(out["schema"]))


def t_an_expressed_format_is_left_alone():
    for good in ("date", "date-time", "time", "uuid"):
        schema = {"type": "object", "properties": {"a": {"type": "string",
                                                         "format": good}}}
        out = T.sanitise_schema(schema)
        check(f"format: {good} is expressed and passes", out["ok"] is True,
              repr(out)[:150])
    out = T.format_for({"type": "object", "properties": {"a": {"format": "email"}}})
    check("an unexpressed format gives no `format` to send",
          out["format"] is None and out["ok"] is False, repr(out)[:160])


def t_unsupported_keywords_names_every_path():
    schema = {"type": "object", "properties": {"a": {"allOf": [{"type": "string"}]},
                                               "b": {"not": {"type": "integer"}}}}
    found = T.unsupported_keywords(schema)
    keys = sorted(k for _w, k, _y in found)
    where = sorted(w for w, _k, _y in found)
    check("both keywords are found", keys == ["allOf", "not"], repr(found))
    check("and each is named at its own dotted path",
          where == ["properties.a.allOf", "properties.b.not"], repr(where))
    check("a plain schema finds nothing", T.unsupported_keywords(PLAIN) == [])
    check("a non-dict finds nothing rather than raising",
          T.unsupported_keywords(None) == [] and T.unsupported_keywords("x") == [])


# --------------------------------------------------------------------------
#   flatten mode
# --------------------------------------------------------------------------

def t_flatten_mode_really_merges_allOf_and_reports_it():
    schema = {"type": "object",
              "properties": {"a": {"allOf": [{"type": "integer"},
                                             {"minimum": 1}]}},
              "required": []}
    out = T.sanitise_schema(schema, on_unsupported=T.FLATTEN)
    check("it is accepted", out["ok"] is True, repr(out)[:200])
    check("the allOf is gone", "allOf" not in repr(out["schema"]), repr(out["schema"]))
    check("what it said was MERGED, not dropped",
          out["schema"]["properties"]["a"].get("type") == "integer"
          and out["schema"]["properties"]["a"].get("minimum") == 1,
          repr(out["schema"]["properties"]["a"]))
    check("and it is on the record as flattened",
          any("allOf" in r for r in out["removed"]), repr(out["removed"]))


def t_flatten_merges_a_top_level_allOf_into_the_parent():
    schema = {"type": "object", "allOf": [{"required": ["b"]},
                                          {"properties": {"b": {"type": "string"}}}]}
    out = T.sanitise_schema(schema, on_unsupported=T.FLATTEN)
    check("it flattens", out["ok"] is True, repr(out)[:200])
    check("the required list came up", out["schema"].get("required") == ["b"],
          repr(out["schema"]))
    check("and the properties came with it",
          out["schema"].get("properties", {}).get("b") == {"type": "string"},
          repr(out["schema"]))


def t_flatten_still_refuses_what_it_cannot_translate():
    """`not` and `if/then/else` have no honest flat form: dropping a NEGATIVE
    constraint makes the schema MORE permissive, which is the unsafe direction."""
    schema = {"type": "object", "properties": {"a": {"not": {"type": "string"}}}}
    out = T.sanitise_schema(schema, on_unsupported=T.FLATTEN)
    check("a lone `not` is still refused, not dropped",
          out["ok"] is False and out["refused"] is True, repr(out)[:220])


def t_a_schema_that_is_not_a_schema_is_refused_not_raised():
    for junk in (None, "x", 3, [], {"type": "object"}):
        out = T.sanitise_schema(junk)
        check(f"{junk!r} gives an answer, not an exception",
              isinstance(out, dict) and "ok" in out and "reason" in out, repr(out)[:120])
    check("a non-dict is refused", T.sanitise_schema(None)["ok"] is False)
    check("an unknown mode is refused",
          T.sanitise_schema(PLAIN, on_unsupported="drop")["ok"] is False,
          repr(T.sanitise_schema(PLAIN, on_unsupported="drop")))


def t_format_for_accepts_all_three_shapes():
    tool = {"name": "get_weather", "parameters": PLAIN}
    wrapped = {"type": "json_schema", "json_schema": {"name": "x", "schema": PLAIN}}
    check("a bare schema works", T.format_for(PLAIN)["format"] == PLAIN)
    check("a tool works", T.format_for(tool)["format"] == PLAIN, repr(T.format_for(tool)))
    check("an OpenAI json_schema wrapper works",
          T.format_for(wrapped)["format"] == PLAIN, repr(T.format_for(wrapped)))


# --------------------------------------------------------------------------
#   The guard
# --------------------------------------------------------------------------

def t_the_guard_passes_the_real_tool_schemas():
    """The measurement that says item 3 was already built: `check_call` reads
    type/required/enum/properties/items, and no real tool schema uses anything
    outside that."""
    try:
        import jarvis_agent as A
    except Exception as exc:
        skip(f"jarvis_agent is not importable here ({type(exc).__name__}); the "
             f"guard is exercised on plain mappings below instead")
        return
    out = T.guard_tool_schemas(A.TOOLS)
    check("the real tool set is guarded", out["checked"] >= 20, repr(out["checked"]))
    check("and every one of them is already validated by check_call",
          out["ok"] is True, repr(out["problems"])[:400])
    check("the guard says what it read",
          out["validated"] == sorted(T.VALIDATED_BY_CHECK_CALL | {"description",
                                                                  "title",
                                                                  "examples",
                                                                  "deprecated",
                                                                  "readOnly",
                                                                  "writeOnly",
                                                                  "$schema",
                                                                  "$id",
                                                                  "$comment",
                                                                  "default"}),
          repr(out["validated"]))


def t_the_guard_FAILS_on_a_keyword_check_call_does_not_read():
    """BITE-PROOF, stated as a test. `minimum` is a real JSON Schema keyword, it
    is EXPRESSED by the grammar, and `jarvis_agent._schema_problems()` does NOT
    read it - so a tool schema using it is validated by nothing. The guard must
    fail, or the hole opens silently."""
    tools = {"calculator": {"type": "object",
                            "properties": {"a": {"type": "integer", "minimum": 1}},
                            "required": ["a"]}}
    out = T.guard_tool_schemas(tools)
    check("the guard FAILS", out["ok"] is False, repr(out))
    check("and names the tool", out["problems"]
          and out["problems"][0]["tool"] == "calculator", repr(out["problems"]))
    check("and the path", out["problems"][0]["path"] == "properties.a.minimum",
          repr(out["problems"]))
    check("and the keyword", out["problems"][0]["keyword"] == "minimum",
          repr(out["problems"]))
    check("and says why it matters",
          "_schema_problems" in out["problems"][0]["why"], repr(out["problems"]))
    # the same shape WITHOUT the unvalidated keyword passes
    ok = T.guard_tool_schemas({"calculator": {"type": "object",
                                              "properties": {"a": {"type": "integer"}},
                                              "required": ["a"]}})
    check("the same tool without `minimum` passes", ok["ok"] is True, repr(ok))
    # and each of the other unvalidated-but-expressed keywords is caught too
    for kw, value in (("pattern", "^[a-z]+$"), ("oneOf", [{"type": "string"}]),
                      ("const", "x"), ("maxLength", 3), ("additionalProperties", False)):
        t = {"t": {"type": "object", "properties": {"a": {kw: value}}}}
        r = T.guard_tool_schemas(t)
        check(f"the guard also catches {kw!r}", r["ok"] is False, repr(r)[:200])


def t_the_guard_accepts_a_plain_mapping_as_well_as_tool_objects():
    class T1:
        parameters = PLAIN
    check("Tool-like objects work",
          T.guard_tool_schemas({"x": T1()})["ok"] is True)
    check("a mapping of schemas works",
          T.guard_tool_schemas({"x": PLAIN})["ok"] is True)
    check("an empty set is not a failure",
          T.guard_tool_schemas({})["ok"] is True, repr(T.guard_tool_schemas({})))
    check("and garbage is a failure, not an exception",
          T.guard_tool_schemas(None)["ok"] is False, repr(T.guard_tool_schemas(None)))


def t_the_guard_agrees_with_the_real_source_of_truth():
    """The guard's reference list is written by hand, so it is checked against
    the function it is about: read `_schema_problems`' own body and confirm the
    keywords it reads match `VALIDATED_BY_CHECK_CALL`."""
    src_path = Path(BACKEND) / "jarvis_agent.py"
    if not src_path.is_file():
        src_path = REPO / "jarvis-backend" / "jarvis_agent.py"
    if not src_path.is_file():
        skip("jarvis_agent.py is not in this checkout, so its body cannot be read")
        return
    src = src_path.read_text(encoding="utf-8", errors="replace")
    body = src[src.index("def _schema_problems"): src.index("def check_call")]
    for kw in T.VALIDATED_BY_CHECK_CALL:
        check(f"check_call really reads {kw!r}", f'"{kw}"' in body or f"'{kw}'" in body,
              f"not found in _schema_problems' body")
    for kw in ("minimum", "maximum", "pattern", "minLength", "oneOf", "const"):
        check(f"and it really does NOT read {kw!r}", f'"{kw}"' not in body,
              f"{kw} found in _schema_problems' body - the list here is stale")


# --------------------------------------------------------------------------
#   What this module does not do
# --------------------------------------------------------------------------

def t_it_approves_nothing_writes_nothing_and_reaches_nothing():
    src = (HERE / "jarvis_tool_schema.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    check("its imports are the standard library only",
          all(m in ("__future__", "copy", "typing") for m in imports),
          repr(sorted(imports)))
    calls = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for forbidden in ("write_text", "mkdir", "open", "urlopen", "check", "approve",
                      "record", "schedule"):
        check(f"it never calls {forbidden}()", forbidden not in calls, repr(sorted(calls)))
    low = ast.unparse(tree).lower()
    for bad in ("approve_all", "auto_approve", "yes_to_all"):
        check(f"no {bad!r} anywhere", bad not in low)
    status = T.status()
    check("it says it sends no schema itself",
          status["schemas_sent_by_this_module"] == 0, repr(status))


def t_no_connection_is_opened_by_any_of_it():
    try:
        socket.socket()
    except AssertionError:
        check("socket.socket() is refused for the whole run", True)
    else:
        check("socket.socket() is refused for the whole run", False,
              "the guard did not install")
    check("and the guard is a class, so `ssl` can still subclass it",
          isinstance(socket.socket, type)
          and socket.socket.__name__ == "_NoNetworkSocket",
          repr(socket.socket))
    import ssl                                        # noqa: F401
    check("importing ssl still works under the guard", hasattr(ssl, "SSLSocket"))


if __name__ == "__main__":
    for fn in (t_a_schema_using_only_expressed_keywords_passes_through_unchanged,
               t_the_four_unexpressed_keywords_are_refused_by_default,
               t_an_expressed_format_is_left_alone,
               t_unsupported_keywords_names_every_path,
               t_flatten_mode_really_merges_allOf_and_reports_it,
               t_flatten_merges_a_top_level_allOf_into_the_parent,
               t_flatten_still_refuses_what_it_cannot_translate,
               t_a_schema_that_is_not_a_schema_is_refused_not_raised,
               t_format_for_accepts_all_three_shapes,
               t_the_guard_passes_the_real_tool_schemas,
               t_the_guard_FAILS_on_a_keyword_check_call_does_not_read,
               t_the_guard_accepts_a_plain_mapping_as_well_as_tool_objects,
               t_the_guard_agrees_with_the_real_source_of_truth,
               t_it_approves_nothing_writes_nothing_and_reaches_nothing,
               t_no_connection_is_opened_by_any_of_it):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
