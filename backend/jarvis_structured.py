"""
jarvis_structured.py - make a malformed tool call structurally impossible.

An 8-billion-parameter model emitting broken JSON is not a rare event, and the
usual answer is to retry until it parses. That wastes a turn, and worse, the
thing it eventually parses is whatever survived several rounds of a model
guessing at its own previous mistake.

Ollama takes a JSON Schema in the `format` field and constrains decoding to it,
so the malformed case stops existing rather than being handled. This module
builds that schema from a tool definition, and validates what comes back.

Two things it deliberately does NOT do.

  * It does not use Outlines or a GBNF grammar. Both were considered; Ollama's
    native structured output reaches the same place without adding a
    dependency or a second inference path to keep in step with the first.

  * It does not tighten the schema beyond shape. A schema narrow enough to
    encode business rules ("path must be under Documents") makes a small model
    worse at the reasoning part, because every token it wanted to emit and
    could not is a token it now has to route around. Shape belongs here; rules
    belong in the gate.

And the rule this module exists to be read alongside: GRAMMAR-VALID IS NOT
AUTHORISED. A perfectly formed `{"tool":"send_email","to":"..."}` is still a
send_email, and it still goes through jarvis_gate exactly as before. Nothing
here is a permission. The validator returns "this is the shape we asked for"
and says nothing at all about whether it should happen.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

# The JSON Schema subset this module emits and understands. Kept deliberately
# small: a validator for the whole specification would be a dependency, and a
# hand-written validator for a subset you do not emit is a liability that looks
# like a feature.
_TYPES = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "array": list, "object": dict}


def schema_for_tool(name: str, params: Optional[dict] = None,
                    required: Optional[list] = None) -> dict:
    """A schema for one tool call.

    `params` maps a parameter name to a type name, or to a small dict of its
    own ({"type": "array", "items": {"type": "string"}}). Anything unknown is
    left unconstrained rather than guessed at - an over-tight schema fails
    closed in the wrong direction here, because the model cannot tell you what
    it wanted to say.
    """
    props: dict = {}
    for key, spec in (params or {}).items():
        if isinstance(spec, str):
            props[key] = {"type": spec if spec in _TYPES else "string"}
        elif isinstance(spec, dict):
            props[key] = spec
        else:
            props[key] = {}
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "const": name},
            "arguments": {"type": "object", "properties": props,
                          "required": list(required or [])},
        },
        "required": ["tool", "arguments"],
    }


def schema_for_choice(tools: list) -> dict:
    """A schema for "pick one of these tools and fill it in".

    Each entry is (name, params, required). The model may only emit a tool
    name from the list, which removes the other common failure: a confident
    call to a tool that does not exist.
    """
    names = [t[0] for t in tools]
    props: dict = {}
    for name, params, _req in tools:
        for key, spec in (params or {}).items():
            props.setdefault(key, {"type": spec} if isinstance(spec, str) else spec)
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": names},
            "arguments": {"type": "object", "properties": props},
        },
        "required": ["tool", "arguments"],
    }


def ollama_body(model: str, prompt: str, schema: Optional[dict] = None,
                *, temperature: float = 0.1, stream: bool = False) -> dict:
    """The request body for /api/generate with decoding constrained.

    `format` takes the schema itself. Passing the string "json" instead is the
    older, looser mode: it guarantees the output parses and guarantees nothing
    about what is in it, which is how a tool call arrives well-formed and
    missing the one field that decides what it touches.
    """
    body: dict = {"model": model, "prompt": prompt, "stream": bool(stream),
                  "options": {"temperature": float(temperature)}}
    if schema:
        body["format"] = schema
    return body


# --------------------------------------------------------------------------
#   Validation
# --------------------------------------------------------------------------
# Constrained decoding is a property of the server that produced the text. A
# response can still arrive from a model that ignored it, a cached reply, a
# proxy, or a version of Ollama too old to understand `format`. So what comes
# back is checked here as well. Belt and braces is the right posture for a
# check that costs microseconds and guards a tool call.

class Invalid(ValueError):
    """The response is not the shape that was asked for."""


def validate(data: Any, schema: dict, path: str = "$") -> list:
    """Returns a list of problems. Empty means it matches.

    Returning problems rather than raising, because the useful thing to do
    with a mismatch is usually to show the owner what was wrong with it.
    """
    problems: list = []
    t = schema.get("type")
    if t and t in _TYPES:
        # bool is a subclass of int in Python, and a boolean arriving where an
        # integer was asked for is exactly the kind of thing that slips past an
        # isinstance check and then behaves strangely three layers later.
        if t in ("integer", "number") and isinstance(data, bool):
            return [f"{path}: expected {t}, got boolean"]
        if not isinstance(data, _TYPES[t]):
            return [f"{path}: expected {t}, got {type(data).__name__}"]

    if "const" in schema and data != schema["const"]:
        problems.append(f"{path}: must be {schema['const']!r}, got {data!r}")
    if "enum" in schema and data not in schema["enum"]:
        problems.append(f"{path}: must be one of {schema['enum']}, got {data!r}")

    if t == "object" and isinstance(data, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in data:
                problems.append(f"{path}.{key}: missing")
        for key, value in data.items():
            if key in props:
                problems += validate(value, props[key], f"{path}.{key}")
    elif t == "array" and isinstance(data, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, value in enumerate(data):
                problems += validate(value, items, f"{path}[{i}]")
    return problems


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse(text: str, schema: Optional[dict] = None) -> dict:
    """Turn a model response into a dict, or raise Invalid.

    Strips a code fence if there is one. A model told to emit JSON that wraps
    it in a fence has not misbehaved in any way worth failing a turn over, and
    refusing it means a retry that produces the same thing.
    """
    raw = (text or "").strip()
    m = _FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise Invalid(f"the response is not JSON ({exc})") from None
    if not isinstance(data, dict):
        raise Invalid(f"expected an object, got {type(data).__name__}")
    if schema:
        problems = validate(data, schema)
        if problems:
            raise Invalid("; ".join(problems[:5]))
    return data


def tool_call(text: str, schema: Optional[dict] = None) -> dict:
    """Parse and validate a tool call, and say plainly that it is not allowed.

    The return value carries `gated: False` for one reason: so that a caller
    reading this code sees, at the point of use, that nothing here has decided
    anything. A shape check is not a permission check, and the gap between
    those two is where an assistant ends up doing something well-formed and
    catastrophic.
    """
    data = parse(text, schema)
    return {"tool": data.get("tool"), "arguments": data.get("arguments") or {},
            "valid_shape": True, "gated": False,
            "note": "shape only - jarvis_gate decides whether this may run"}


# --------------------------------------------------------------------------
#   The schema the memory extractor uses
# --------------------------------------------------------------------------
# Concrete rather than illustrative: this is the one place in this repository
# that already asks a local model for JSON, and it asked with format="json",
# which promises only that the reply parses. A reply of `{}` parses.
FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "replaces": {},                     # string or null
                    "confidence": {"type": "number"},
                },
                "required": ["text"],
            },
        }
    },
    "required": ["facts"],
}


def status() -> dict:
    return {"available": True,
            "note": ("Constrained decoding shapes a tool call. It never "
                     "authorises one.")}
