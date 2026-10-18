"""test_tool_schema_wiring.py - the shipped schema sanitiser wired into the chat loop.

`jarvis_tool_schema` (#461, shipped, previously called by nothing) is applied on
BOTH sides of a tool call now (Part III.1 item 4, 2026-10-18):

  * OUTGOING: every schema put in a request's `tools` list goes through
    `sanitise_schema()` (default REFUSE) and then `guard_tool_schemas()` - the
    schema must be one the local model's grammar really expresses AND one
    `jarvis_agent._schema_problems()` really validates. A tool that fails either
    is NOT sent, never sent weakened.
  * INCOMING: `check_call()` validates the parsed arguments against THE SAME
    sanitised schema that was sent, before `prepare()` or the gate.
  * FAIL CLOSED, IN PLAIN WORDS: if the model calls a tool whose schema could
    not be sent (it may remember the name from an earlier turn), the call is not
    silently dropped - the model gets a plain refusal naming the tool, saying
    nothing ran, and telling it to tell the owner.

Runs with no Ollama, no network, no model: the real `run_local_turn` loop with a
scripted model, the project's own fakes (test_agent.NoRealIO / scripted_stream),
and the REAL shipped modules. Every check bites - the mutation record is in the
build report.

    python -B backend/test_tool_schema_wiring.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_tool_schema.py")
sys.path.append(str(HERE / "rebuilt"))

import jarvis_agent as AG  # noqa: E402
import jarvis_tool_schema as TS  # noqa: E402
from test_agent import NoRealIO, allow, scripted_stream  # noqa: E402

# The owner's manner line has its own suite; a turn here is about tools only.
AG._manner_now = lambda *a, **k: None

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The turn harness: the real loop, a scripted model, no IO
# --------------------------------------------------------------------------

def _call(name, args):
    return {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}


def _answer(text="done"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _turn(responses, enabled, *, can_use_tools=True):
    """(request bodies, tool-result texts) from one real local turn."""
    opener, bodies = scripted_stream(responses)
    streamed = []
    real_can = AG._model_can_use_tools
    AG._model_can_use_tools = lambda url, model: can_use_tools
    try:
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "go", "provenance": "typed"}],
                "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                stream_out=streamed.append, gate_check=allow, open_stream=opener,
                enabled_tools=set(enabled), record_chain=lambda steps: None,
                on_step=lambda step: None, lane_choice=None)
    finally:
        AG._model_can_use_tools = real_can
    results = [m.get("content", "") for m in (bodies[-1]["messages"] if bodies else [])
               if m.get("role") == "tool"]
    return bodies, results


def _sent_tool_names(bodies):
    body = bodies[0] if bodies else {}
    return [t.get("function", {}).get("name") for t in body.get("tools") or []]


def _probe(name, parameters):
    """A Tool whose execute records that it ran (it never should for a refused
    schema; it SHOULD be hit by the control cases)."""
    ran = []

    def execute(args, state, **_kw):
        ran.append(dict(args))
        return {"ok": True, "ran": True}

    tool = AG.Tool(name, f"a probe tool called {name}", parameters,
                   lambda args: (None, f"Use {name}"), execute)
    return tool, ran


class _Added:
    """Temporarily put a probe Tool in AG.TOOLS (and take it out again)."""

    def __init__(self, tool):
        self.tool = tool

    def __enter__(self):
        AG.TOOLS[self.tool.name] = self.tool
        return self.tool

    def __exit__(self, *a):
        AG.TOOLS.pop(self.tool.name, None)
        return False


# --------------------------------------------------------------------------
#   1. A schema the local grammar would believe and not enforce is not sent
# --------------------------------------------------------------------------

def t_an_unexpressible_schema_is_not_sent_and_its_call_is_refused():
    """`allOf` is the module's own measured example: the grammar accepts it and
    ignores it. Such a tool must not be sent, but a call to it must not vanish."""
    bad = {"type": "object",
           "allOf": [{"properties": {"n": {"type": "integer"}}}],
           "required": ["n"]}
    tool, ran = _probe("schema_probe_allof", bad)
    with _Added(tool):
        bodies, results = _turn([_call("schema_probe_allof", {"n": 1}),
                                 _answer("done")],
                                {"schema_probe_allof", "calculator"})
    names = _sent_tool_names(bodies)
    check("a tool whose schema the grammar would only IGNORE is not in the request",
          "schema_probe_allof" not in names, names)
    check("... and an ordinary tool is still sent (not a blanket loss)",
          "calculator" in names, names)
    check("... and its execute() never ran", ran == [], ran)
    check("the model gets a plain refusal naming the tool, saying nothing ran, and "
          "telling it to tell the owner",
          bool(results) and all(
              word in results[0] for word in
              ("schema_probe_allof", "was not run", "Nothing was run",
               "Tell the owner")), results)
    check("the call was not SILENTLY dropped: a tool result came back for it",
          bool(results) and "was not run" in results[0], results)
    names_all = {"schema_probe_allof", "calculator"}
    args, problem = AG.check_call(
        "schema_probe_allof", {"n": 1}, names_all,
        dict(AG.TOOLS, schema_probe_allof=tool))
    check("check_call itself refuses it in plain words, before prepare() or the gate",
          args is None and problem is not None and "was not run" in problem
          and "not offered" in problem and "Nothing was run" in problem, problem)


# --------------------------------------------------------------------------
#   2. A keyword the grammar expresses but Jarvis cannot VALIDATE is refused too
# --------------------------------------------------------------------------

def t_a_constraint_jarvis_cannot_validate_blocks_the_tool():
    """`minimum` is a real keyword the grammar expresses, but `_schema_problems`
    does not read it - so the constraint would be checked by nobody. The wiring
    must leave the tool out rather than run a call it cannot validate."""
    tool, ran = _probe("schema_probe_min", {
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 1}},
        "required": ["n"]})
    with _Added(tool):
        bodies, results = _turn([_call("schema_probe_min", {"n": 0}),
                                 _answer("done")],
                                {"schema_probe_min", "calculator"})
        args, problem = AG.check_call(
            "schema_probe_min", {"n": 0}, {"schema_probe_min"},
            dict(AG.TOOLS, schema_probe_min=tool))
    names = _sent_tool_names(bodies)
    check("a schema using a keyword check_call does not read is not sent",
          "schema_probe_min" not in names, names)
    check("... its execute() never ran", ran == [], ran)
    check("... and the plain refusal names the keyword it could not check",
          args is None and problem is not None and "minimum" in problem
          and "cannot check" in problem, problem)


# --------------------------------------------------------------------------
#   3. What was sent is what gets validated
# --------------------------------------------------------------------------

def t_the_schema_sent_is_the_schema_validated():
    """The strongest wiring claim: patch the shipped sanitiser to add a required
    field, and the turn must BOTH send that field's requirement to the model AND
    reject a call that does not have it - raw `parameters` never had it."""
    real_sanitise = TS.sanitise_schema

    def sanitise_with_extra(schema, **kw):
        out = real_sanitise(schema, **kw)
        if out.get("ok") and isinstance(out.get("schema"), dict):
            sent = out["schema"]
            sent.setdefault("properties", {})["wiring_extra"] = {"type": "string"}
            req = sent.setdefault("required", [])
            if isinstance(req, list) and "wiring_extra" not in req:
                req.append("wiring_extra")
        return out

    TS.sanitise_schema = sanitise_with_extra
    try:
        bodies, results = _turn([_call("calculator", {"expression": "1 + 1"}),
                                 _answer("done")], {"calculator"})
    finally:
        TS.sanitise_schema = real_sanitise
    sent = next((t for t in (bodies[0].get("tools") or [])
                 if t["function"]["name"] == "calculator"), None)
    sent_params = (sent or {}).get("function", {}).get("parameters") or {}
    check("the sanitiser's output is what the request carries (its added field is "
          "in the sent schema)", "wiring_extra" in (sent_params.get("properties") or {}),
          sent_params)
    check("a call valid under the RAW schema but not the SENT one is refused",
          bool(results) and "wiring_extra" in results[0], results)
    check("... and stays the plain 'arguments are wrong' refusal, not a crash",
          bool(results) and "arguments are wrong" in results[0], results)
    args, problem = AG.check_call("calculator", {"expression": "1 + 1"},
                                  {"calculator"}, AG.TOOLS)
    check("with the real sanitiser back, the same call passes check_call again",
          args is not None and problem is None, problem)


# --------------------------------------------------------------------------
#   4. The real tool set is unchanged (this wiring changes no current tool)
# --------------------------------------------------------------------------

def t_the_real_tool_set_is_sent_unchanged():
    names = list(AG.TOOLS)
    schemas = AG._schemas_for(names, [], {})
    sent = {t["function"]["name"]: t for t in schemas}
    check(f"every one of the {len(names)} real tools is still sent (none blocked)",
          len(schemas) == len(names) and set(sent) == set(names),
          (len(schemas), len(names)))
    differing = [n for n in names
                 if sent[n]["function"]["parameters"] != AG.TOOLS[n].parameters]
    check("... each one's parameters are the same object as before (deep-equal)",
          differing == [], differing)
    sent_guard = TS.guard_tool_schemas(
        {n: {"parameters": sent[n]["function"]["parameters"]} for n in names})
    check("... every schema actually SENT passes the shipped guard",
          sent_guard["ok"] is True, sent_guard["problems"])
    raw_cost = AG.estimate_tokens([AG.TOOLS[n].schema(names) for n in names])
    check("... so the tool-text budget is unchanged by the wiring",
          AG.tool_text_tokens(names) == raw_cost,
          (AG.tool_text_tokens(names), raw_cost))


# --------------------------------------------------------------------------
#   5. Plug-in programs' tools go through the same check
# --------------------------------------------------------------------------

def t_plugin_tools_are_checked_too():
    bad, bad_ran = _probe("plugin_bad", {
        "type": "object",
        "not": {"type": "object"}})
    good, _good_ran = _probe("plugin_good", {
        "type": "object",
        "properties": {"n": {"type": "integer"}}})
    extra = {"plugin_bad": bad, "plugin_good": good}
    schemas = AG._schemas_for(["calculator"], [], extra)
    names = [t["function"]["name"] for t in schemas]
    check("a plug-in tool with an unexpressible schema is not sent",
          "plugin_bad" not in names, names)
    check("... a plug-in tool with an honest schema still is",
          "plugin_good" in names and "calculator" in names, names)
    args, problem = AG.check_call("plugin_bad", {}, {"plugin_bad", "plugin_good"},
                                  dict(AG.TOOLS, **extra))
    check("... and calling the blocked plug-in tool is a plain refusal, not silence",
          args is None and problem is not None and "was not run" in problem
          and "Nothing was run" in problem, problem)


# --------------------------------------------------------------------------
#   6. A backend without the module keeps today's behaviour (documented)
# --------------------------------------------------------------------------

def t_without_the_module_nothing_is_taken_away():
    """The module is SHIPPED, so this is the older-backend path only. It must be
    today's behaviour - schemas sent as they are - not every tool refused."""
    real = AG._tool_schema_module
    AG._tool_schema_module = lambda: None
    try:
        params, why = AG._parameters_to_send(AG.TOOLS["calculator"])
        schemas = AG._schemas_for(["calculator"], [], {})
    finally:
        AG._tool_schema_module = real
    check("no module: a normal tool's parameters are returned unchanged",
          params == AG.TOOLS["calculator"].parameters and why == "", (params, why))
    check("no module: the tool is still sent (a missing module never empties the list)",
          [t["function"]["name"] for t in schemas] == ["calculator"], schemas)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
