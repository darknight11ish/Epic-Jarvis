#!/usr/bin/env python3
"""jarvis_tool_schema.py - what a JSON Schema may say before it is sent as
Ollama's `format`, and what a TOOL's schema must say to be checked at all.

WHY THIS FILE EXISTS, AND WHAT IT DELIBERATELY DOES NOT DO

It does not put a tool's schema into the tool-calling request, and that is a
measured decision rather than a preference. On the live Ollama this project
runs (0.40.5, 127.0.0.1:11434), measured 2026-10-15 with `qwen3:0.6b`,
temperature 0, `reasoning_effort: "none"` (plain `think:false` is IGNORED on
/v1 and the whole budget goes to `reasoning`, which is why a first pass of
probes returned empty content):

    /v1/chat/completions  tools alone
        -> finish_reason "tool_calls", arguments '{"city":"Paris"}'      CORRECT
    /v1/chat/completions  tools + format=<the tool's own schema>
        -> finish_reason "tool_calls", arguments
           '{"city":{"type":"string","value":"Paris"}}'
        THE ARGUMENTS ARE CORRUPTED: the schema leaked into the value.
    /v1/chat/completions  tools + response_format json_schema
        -> finish_reason "stop", NO tool call, content '{"city": "Paris"}'
    /api/chat             tools alone
        -> tool_calls=[get_weather(city=Paris)]                          CORRECT
    /api/chat             tools + format=<schema>
        -> tool_calls=None, content '{"city": "Paris"}'   THE TOOL CALL IS GONE

So the schema belongs in `format` only on a call that offers no `tools`. This
module gives that call a safe schema and refuses the unsafe ones; it does not
touch the tool loop. Getting grammar-validated ARGUMENTS would mean a separate
single-tool call with no `tools` field, which is a design change with its own
decision and is NOT built here.

WHAT IS MEASURED, AND HOW. The method: hand the schema to the live Ollama as
`format`, then order the model to emit a value that VIOLATES the keyword. If the
output cannot violate it, the grammar expresses it. Every line below was
measured in both directions where one direction would have been ambiguous.

  EXPRESSED (so passing them through is honest):
    type (incl. a list of types), enum, const, oneOf, anyOf, $ref/$defs,
    $ref/definitions, pattern, patternProperties, additionalProperties,
    minimum, maximum, minLength, maxLength, maxItems, `format` for date and
    uuid.
  NOT EXPRESSED - accepted, then silently ignored, so the constraint is a lie:
    allOf           `allOf:[{type:integer}]`, asked for a string -> {"a": {}}.
    not             `not:{type:integer}`, asked for a number    -> {"a": 5}.
    if/then/else    `else:{required:[c]}`, asked for the answer -> no "c".
    format: email   asked for "hello"                          -> {"a": "hello"}.
  NOT ESTABLISHED, and not claimed either way: `minItems`. With
  `minItems:3, maxItems:3` and a prompt asking for `[]` the grammar produced ONE
  element, so minItems was not enforced in that observation; `maxItems:1` with
  three requested produced one element, which is consistent with enforcement.
  One observation each on a 0.6B model is not evidence, so nothing here refuses
  or rewrites `minItems`.

TWO NUMBERS FROM THE REAL SCHEMAS, so the value of this module is not overstated:

  1. `jarvis_agent.TOOLS` was censused - 31 tools. Across all of them the only
     keywords used are `type` (167), `properties` (36), `required` (28),
     `enum` (10), `items` (13), `description` (48) and `title` (1). Not one tool
     schema uses allOf, not, if/then/else, $ref, oneOf, format, minimum or
     anything else this module refuses. So NOTHING IS BROKEN TODAY, and this
     module does not fix a present bug.
  2. Every other schema sent as `format` in this repository was censused too -
     `jarvis_structured.FACTS_SCHEMA`, `jarvis_chatbot.SUMMARY_SCHEMA`,
     `jarvis_chatbot_compare.SUMMARY_SCHEMA`, `jarvis_support.SUMMARY_SCHEMA`,
     `jarvis_tidy.SCHEMA`, `jarvis_wiki.ANALYSIS_SCHEMA`,
     `jarvis_prompt_coach.SCHEMA` - and EXACTLY ONE keyword appears in any of
     them: prompt_coach's `minimum`/`maximum`, which IS expressed.

So the honest value of `sanitise_schema()` is that a FUTURE schema cannot
silently no-op. That is what it is for, and it is why the default is to REFUSE
rather than to drop quietly.

AND THE SECOND HALF, WHICH IS THE ONE WITH A REAL GAP TO CLOSE TODAY.
`jarvis_agent.check_call()` (:4053) already validates a parsed tool call against
the tool's own schema through `_schema_problems()` (:4017), before prepare() and
before the gate (:8168). It reads `type`, `required`, `enum`, `properties` and
`items`. No tool schema uses anything else - so nothing is unvalidated today.
`guard_tool_schemas()` is the guard that keeps that true: it fails the moment a
tool schema uses a keyword `_schema_problems` does not read, so the hole cannot
open silently the way the `**_extra` hole did (jarvis_router.py:632-648).

STANDARD LIBRARY ONLY. It approves nothing, writes nothing, sends nothing and
reaches no network: it takes a dict and returns a dict.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

#: The keywords the live grammar was measured to EXPRESS. A schema using only
#: these is passed through unchanged.
EXPRESSED = frozenset({
    "type", "properties", "required", "enum", "const", "items", "oneOf",
    "anyOf", "$ref", "$defs", "definitions", "pattern", "patternProperties",
    "additionalProperties", "minimum", "maximum", "minLength", "maxLength",
    "maxItems", "description", "title", "default",
})

#: Accepted, then IGNORED. Each one is a constraint a reader would believe.
#: `allOf` is the only one with a safe flattening; the other two are not
#: expressible at all, so there is nothing honest to translate them into.
NOT_EXPRESSED = {
    "allOf": ("conjunction - the grammar accepts it and then ignores it "
              "(measured: allOf:[{type:integer}] answered a string request "
              "with an object)"),
    "not": ("negation - the grammar accepts it and then ignores it (measured: "
            "not:{type:integer} answered a number request with a number)"),
    "if": ("conditional - the grammar accepts it and then ignores it (measured: "
           "an `else` branch requiring a field produced no such field)"),
    "then": "conditional - part of if/then/else, which is not expressed",
    "else": "conditional - part of if/then/else, which is not expressed",
}

#: `format` values the grammar was measured to express. Any other value is a
#: no-op and is refused by default: a schema that says `format: email` and gets
#: no enforcement is worse than one that says nothing, because it is believed.
FORMAT_EXPRESSED = frozenset({"date", "date-time", "time", "uuid"})

#: Every keyword `jarvis_agent._schema_problems()` (:4017) actually reads. This
#: is the guard's reference list, and it is deliberately explicit rather than
#: derived, so a change to that function has to be matched here by hand.
VALIDATED_BY_CHECK_CALL = frozenset({"type", "required", "enum", "properties",
                                     "items"})

#: Harmless wherever they appear: they change no verdict.
_METADATA = frozenset({"description", "title", "examples", "deprecated",
                       "readOnly", "writeOnly", "$schema", "$id", "$comment",
                       "default"})

#: How `sanitise_schema` treats an unexpressed keyword.
REFUSE = "refuse"       # default: refuse the whole schema, naming the keyword
FLATTEN = "flatten"     # merge `allOf` upward, drop the rest, and report it


#: The keywords whose VALUE is a MAP OF SCHEMAS rather than a schema. Their keys
#: are property names, not keywords, and must not be reported as keywords - the
#: first version of this file did exactly that and reported `properties.a` as an
#: unknown keyword called `a`, which would have made the guard cry wolf on the
#: real tool set.
_MAP_KEYWORDS = ("properties", "patternProperties", "$defs", "definitions")


def _walk(node, path=""):
    """(dotted path, keyword, value) for every KEYWORD in the tree.

    Descends through everything, but does not treat the keys of `properties`,
    `patternProperties`, `$defs` or `definitions` as keywords.
    """
    if isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        where = f"{path}.{key}" if path else key
        yield where, key, value
        if key in _MAP_KEYWORDS and isinstance(value, dict):
            for name, sub in value.items():
                yield from _walk(sub, f"{where}.{name}")
        elif isinstance(value, (dict, list, tuple)):
            yield from _walk(value, where)


def unsupported_keywords(schema: Any) -> list:
    """Every unexpressed keyword in `schema`, as `(where, keyword, why)`.

    A total function: anything that is not a dict gives `[]` rather than raising,
    because "this is not a schema" is a different question from "this schema is
    safe", and the caller below refuses it separately.
    """
    out = []
    if not isinstance(schema, dict):
        return out
    for where, key, value in _walk(schema):
        if key in NOT_EXPRESSED:
            out.append((where, key, NOT_EXPRESSED[key]))
        elif key == "format" and isinstance(value, str) \
                and value not in FORMAT_EXPRESSED:
            out.append((where, "format", (
                f"`format: {value}` is not expressed - measured: `format: email` "
                f"handed back the very string it was asked to reject")))
    return out


def sanitise_schema(schema: Any, *, on_unsupported: str = REFUSE) -> dict:
    """`{"ok", "schema", "refused", "removed", "reason"}` for one schema.

    DEFAULT: REFUSE. A dropped constraint is a constraint the caller still
    believes in, and a schema that silently loses it is exactly the failure this
    module exists to prevent - so the default answer to "I cannot express this"
    is "then do not send it", not "send it anyway".

    `on_unsupported="flatten"` merges `allOf` upward (its members' `properties`,
    `required` and `type` are shallow-merged into the parent, which is what
    `allOf` means for the flat schemas here) and DROPS `not`/`if`/`then`/`else`
    and an unexpressed `format`, reporting every one in `removed`. A caller that
    picks this mode is accepting a weaker schema on the record, in writing.

    Never raises, whatever it is handed.
    """
    if not isinstance(schema, dict):
        return {"ok": False, "schema": None, "refused": True, "removed": [],
                "reason": "not a JSON Schema object"}
    if on_unsupported not in (REFUSE, FLATTEN):
        return {"ok": False, "schema": None, "refused": True, "removed": [],
                "reason": f"on_unsupported must be {REFUSE!r} or {FLATTEN!r}"}
    problems = unsupported_keywords(schema)
    if not problems:
        return {"ok": True, "schema": copy.deepcopy(schema), "refused": False,
                "removed": [], "reason": ""}

    if on_unsupported == REFUSE:
        named = "; ".join(f"{w} ({k}: {why})" for w, k, why in problems[:4])
        more = len(problems) - 4
        return {"ok": False, "schema": None, "refused": True, "removed": [],
                "reason": ("this schema uses a keyword the grammar does not "
                           f"express, so it would be believed and not enforced: "
                           f"{named}"
                           + (f"; and {more} more" if more > 0 else ""))}

    # FLATTEN. `allOf` is merged upward for real; a NEGATIVE or CONDITIONAL
    # constraint has no honest flat form - dropping `not` makes the schema MORE
    # permissive, which is the unsafe direction - so it is still refused.
    out = copy.deepcopy(schema)
    removed = []
    for _ in range(6):                       # bounded: a nested allOf cannot loop
        found = unsupported_keywords(out)
        if not found:
            break
        progressed = False
        for where, key, _why in found:
            parent, last = _parent_and_key(out, where)
            if not isinstance(parent, dict) or last not in parent:
                continue
            if key == "allOf" and isinstance(parent.get("allOf"), list):
                members = parent.pop("allOf")
                removed.append(where)
                for member in members:
                    if isinstance(member, dict):
                        _merge_into(parent, member)
                progressed = True
            elif key == "format":
                parent.pop("format", None)
                removed.append(where)
                progressed = True
            else:
                return {"ok": False, "schema": None, "refused": True,
                        "removed": removed,
                        "reason": (f"{key!r} at {where} has no flat form: dropping a "
                                   f"negative or conditional constraint makes the "
                                   f"schema MORE permissive, so it is refused "
                                   f"rather than sent without it")}
        if not progressed:
            break
    left = unsupported_keywords(out)
    if left:
        return {"ok": False, "schema": None, "refused": True, "removed": removed,
                "reason": ("could still not flatten "
                           + ", ".join(k for _w, k, _y in left))}
    return {"ok": True, "schema": out, "refused": False, "removed": removed,
            "reason": ("flattened/dropped " + ", ".join(removed)
                       if removed else "")}


def _merge_into(parent: dict, member: dict) -> None:
    """Fold one `allOf` member into the schema that contained it. Shallow on
    purpose: the schemas here are flat, and a deep merge would have to decide
    what to do about conflicting keys, which is a different feature."""
    for mk, mv in member.items():
        if mk == "properties" and isinstance(mv, dict):
            have = parent.setdefault("properties", {})
            if isinstance(have, dict):
                for pk, pv in mv.items():
                    have.setdefault(pk, pv)
        elif mk == "required" and isinstance(mv, list):
            have = parent.setdefault("required", [])
            if isinstance(have, list):
                for r in mv:
                    if r not in have:
                        have.append(r)
        elif mk == "type" and "type" not in parent:
            parent["type"] = mv
        elif mk in NOT_EXPRESSED:
            continue                     # reported by the caller, never merged
        else:
            parent.setdefault(mk, mv)


def _parent_and_key(root: Any, where: str):
    """`(the dict holding `where`, its last part)`, or `(None, None)`.

    The first version of this returned the node AT the path, so `allOf`'s
    container came back as the member LIST and flatten reported "could still not
    flatten" while doing nothing. The container is the PARENT.
    """
    parts = _split_path(where)
    if not parts or any(p is None for p in parts):
        return None, None
    node = root
    for part in parts[:-1]:
        if isinstance(node, list):
            if not isinstance(part, int) or part >= len(node):
                return None, None
            node = node[part]
        elif isinstance(node, dict):
            if part not in node:
                return None, None
            node = node[part]
        else:
            return None, None
    return (node, parts[-1]) if isinstance(node, (dict, list)) else (None, None)


def _split_path(where: str) -> list:
    out, buf, i = [], "", 0
    while i < len(where):
        ch = where[i]
        if ch == ".":
            if buf:
                out.append(buf)
                buf = ""
        elif ch == "[":
            if buf:
                out.append(buf)
                buf = ""
            j = where.find("]", i)
            if j < 0:
                return [None]
            try:
                out.append(int(where[i + 1:j]))
            except ValueError:
                return [None]
            i = j
        else:
            buf += ch
        i += 1
    if buf:
        out.append(buf)
    return out


def format_for(schema_or_tool: Any, *, on_unsupported: str = REFUSE) -> dict:
    """The `format` value for ONE schema, or for an object carrying one.

    Accepts a bare schema, or an object with `parameters` (a tool), or an object
    with `schema` (an OpenAI-style `json_schema` wrapper), so a caller does not
    have to know which shape it is holding. Returns `sanitise_schema`'s answer
    with `format` set to the schema to send, or None when it is refused.
    """
    target = schema_or_tool
    if isinstance(schema_or_tool, dict):
        if isinstance(schema_or_tool.get("parameters"), dict):
            target = schema_or_tool["parameters"]
        elif isinstance(schema_or_tool.get("schema"), dict):
            target = schema_or_tool["schema"]
        else:
            inner = schema_or_tool.get("json_schema")
            if isinstance(inner, dict) and isinstance(inner.get("schema"), dict):
                target = inner["schema"]
    out = sanitise_schema(target, on_unsupported=on_unsupported)
    out["format"] = out.get("schema") if out.get("ok") else None
    return out


def guard_tool_schemas(tools: Any, *, validated=None) -> dict:
    """THE GUARD: does every tool schema stay inside what `check_call` reads?

    `jarvis_agent.check_call()` validates a parsed call against
    `tools[name].parameters` through `_schema_problems()`, which reads `type`,
    `required`, `enum`, `properties` and `items` and NOTHING else. A tool schema
    that starts using `minimum`, `pattern`, `oneOf`, `const` or anything else
    would be validated by nothing - the call would pass and the constraint would
    be decorative.

    Returns `{"ok", "problems": [...], "checked": n, "validated": [...]}`. A
    problem names the tool, the path and the keyword, so the fix is obvious.
    `tools` may be `jarvis_agent.TOOLS` (Tool objects with `.parameters`), or a
    plain `{name: schema}` mapping - both are accepted, because a suite should
    not have to build Tool objects to ask this question.
    """
    known = set(validated or VALIDATED_BY_CHECK_CALL) | set(_METADATA)
    problems, checked = [], 0
    if not isinstance(tools, dict):
        return {"ok": False, "problems": [{"tool": "", "path": "",
                                           "keyword": "",
                                           "why": "not a mapping of tools"}],
                "checked": 0, "validated": sorted(known)}
    for name, tool in tools.items():
        schema = tool
        if not isinstance(tool, dict) or "parameters" in tool:
            schema = getattr(tool, "parameters", None)
            if schema is None and isinstance(tool, dict):
                schema = tool.get("parameters")
        if not isinstance(schema, dict):
            continue
        checked += 1
        for where, key, _value in _walk(schema):
            if key in known:
                continue
            problems.append({"tool": str(name), "path": where, "keyword": key,
                             "why": (f"{key!r} is not read by "
                                     f"jarvis_agent._schema_problems(), so a call "
                                     f"that breaks it still runs")})
    return {"ok": not problems, "problems": problems, "checked": checked,
            "validated": sorted(known),
            "note": ("A schema keyword outside this list is validated by nothing. "
                     "Either teach _schema_problems() to read it or stop using "
                     "it - do not leave it decorative.")}


def status() -> dict:
    """What this module refuses and what it checks, for a banner or a suite."""
    return {"module": "jarvis_tool_schema", "version": 1,
            "expressed": sorted(EXPRESSED),
            "not_expressed": sorted(NOT_EXPRESSED),
            "format_expressed": sorted(FORMAT_EXPRESSED),
            "validated_by_check_call": sorted(VALIDATED_BY_CHECK_CALL),
            "default_mode": REFUSE,
            "schemas_sent_by_this_module": 0}
