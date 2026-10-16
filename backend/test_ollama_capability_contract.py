"""test_ollama_capability_contract.py - the Ollama contract Jarvis reads, pinned.

    python3 backend/test_ollama_capability_contract.py

WHY THIS EXISTS. Jarvis is CAPABILITY-DRIVEN, NOT VERSION-GATED - a deliberate
choice, and the right one (`jarvis_hardware.py:912`: "By the cards alone, so a
new Ollama version does not forget that a size did not fit"). It never branches
on Ollama's version; it asks at runtime what a model can do. Three reads do it:

  * `_model_can_use_tools()`   - /api/show -> "capabilities" -> "tools"
  * `_model_can_see_pictures()` - /api/show -> "capabilities" -> "vision"
  * `_lookup_context()`         - /api/ps, then /api/show -> "parameters"

THE WEAKNESS THIS GUARDS. If a future Ollama renames one of those strings, or
moves a field, those reads start returning None. Jarvis then degrades SAFELY -
`None` means "Ollama did not say", so a turn still offers tools and a picture is
still kept (`keep_picture=sees is None`) - but it degrades SILENTLY: tool use or
picture reading can go quiet with no error and no failing test. This suite is
that failing test.

WHY THIS IS MOSTLY STATIC, AND WHY THE OTHER HALF IS STUBBED.

A STUB CANNOT DETECT A CONTRACT CHANGE. A stub is written from the same
assumption as the code it feeds: a test that answers `{"capabilities": ["tools"]}`
passes whether or not Ollama still calls that field `capabilities`, because the
stub supplies the field name the code already expects. Only pinning the literal
against the source - or asking a real Ollama, which CI cannot do - can catch a
rename. So the CONTRACT half reads `jarvis_agent.py` itself: the vocabulary, the
field names and the endpoints, each with the line it came from.

STATIC TEXT CANNOT PROVE THE THREE STATES. Whether `[]` or a non-list answers
None, and whether None still means "offer tools anyway", is behaviour. So the
SEMANTICS half drives the real functions with `_get_json` stubbed - no Ollama,
no socket, no network. Both halves run on a checkout with nothing installed.

NO VERSION CHECK, ON PURPOSE. A guard that pinned Ollama's version number would
be worse than none: the whole design is that a new version must not make Jarvis
forget what it can do. What is pinned is the *vocabulary and shape* Jarvis
depends on, so a change is a loud, one-line fix rather than a silent regression.

WHAT THIS CANNOT VERIFY, SAID PLAINLY. The module cites Ollama's own source
files in comments (`ollama/server/routes.go`, `ollama/openai/openai.go`,
`middleware/openai.go`) - 7 such citations, at 3133, 3268, 3270, 3389, 3392,
3447 and 6585. Those files are NOT in this repository, so nothing here can check
the citations, and this suite does not pretend to: it pins what Jarvis READS,
which is all a checkout can prove. None of the seven is about capabilities -
they are about streaming, think-parsing and cached tokens - so there is also no
citation tying "tools"/"vision" to an Ollama source file. That gap is recorded,
not papered over.

A NAME COLLISION TO KNOW ABOUT, because a grep misleads here: the word
"capabilities" appears 5 times in this module, and only 3 are Ollama's field.
`_prepare_github_search` reads `args.get("capabilities")` (line 641) and the
`github_search` tool DECLARES a `capabilities` argument (line 1798) - those are
the tool's own parameters, nothing to do with a model's capabilities. The pins
below are scoped to the three functions that read Ollama, so the tool's argument
is neither pinned nor mistaken for the field. `_lookup_context`'s own docstring
(line 3657) is the third mention.
"""
from __future__ import annotations

import ast
import contextlib
import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import BACKEND, REPO, missing  # noqa: E402

sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

# --------------------------------------------------------------------------
#   THE PIN - every line here came from a line of backend/jarvis_agent.py
# --------------------------------------------------------------------------
#
#: The capability STRINGS Jarvis compares against. Renaming either is a
#: contract change, and the pin is the point: update it deliberately.
CAPABILITY_TOOLS = "tools"      # jarvis_agent.py:3668  `can = "tools" in caps`
CAPABILITY_VISION = "vision"    # jarvis_agent.py:5742  `sees = "vision" in caps`

#: The field the capabilities list is read from, on /api/show.
SHOW_FIELD = "capabilities"     # jarvis_agent.py:3666 and :5740

#: The /api/ps fields `_lookup_context` reads, and the /api/show one it
#: falls back to. Source: jarvis_agent.py:3622-3635.
PS_ENDPOINT = "/api/ps"
PS_FIELDS = ("models", "name", "model", "context_length")
SHOW_ENDPOINT = "/api/show"
SHOW_PARAM_FIELD = "parameters"
NUM_CTX_RE = "num_ctx"

#: The two functions that read capabilities, and the helper that reads the
#: context length. Named so a rename is a loud failure, not a silent skip.
TOOLS_FN = "_model_can_use_tools"
SEES_FN = "_model_can_see_pictures"
CONTEXT_FN = "_lookup_context"
ALLOWED_FN = "_allowed_tools"

#: The documented three-state wiring, pinned as text because it IS the contract:
#: `None` must keep the picture and must not remove the tools. A change to
#: either line is a behaviour change and has to be made deliberately.
KEEP_PICTURE_ON_UNKNOWN = "keep_picture=sees is None"     # jarvis_agent.py:7721
TOOLS_REMOVED_ONLY_ON_FALSE = "is False"                  # jarvis_agent.py:6815


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print("skip  " + why)


# ==========================================================================
#   Reading the module's own source
# ==========================================================================

AGENT = BACKEND / "jarvis_agent.py"


def _parse():
    """(the module's AST, its source text) - or (None, None) if unreadable."""
    if not AGENT.is_file():
        return None, None
    text = AGENT.read_text(encoding="utf-8", errors="replace")
    try:
        return ast.parse(text), text
    except SyntaxError:
        return None, text


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _caps_var(fn):
    """The local name bound from `.get("capabilities")`, or None.

    This is what ties the pin to the FIELD: a function that stopped reading
    `capabilities` has no such name, so its vocabulary reads as empty and the
    checks below fail rather than passing over nothing."""
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get" and node.value.args):
            continue
        first = node.value.args[0]
        if isinstance(first, ast.Constant) and first.value == SHOW_FIELD:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    return target.id
    return None


def _vocabulary(fn):
    """The string literals this function compares the capabilities list against."""
    name = _caps_var(fn)
    if name is None:
        return set()
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        other = []
        if isinstance(node.left, ast.Name) and node.left.id == name:
            other = list(node.comparators)
        elif any(isinstance(c, ast.Name) and c.id == name for c in node.comparators):
            other = [node.left]
        for side in other:
            if isinstance(side, ast.Constant) and isinstance(side.value, str):
                out.add(side.value)
    return out


def _get_fields(fn):
    """Every string passed to `.get(...)` inside a function."""
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                out.add(first.value)
    return out


def _segment(tree, text, name):
    """The source text of one function, or ""."""
    fn = _func(tree, name)
    if fn is None:
        return ""
    try:
        return ast.get_source_segment(text, fn) or ""
    except Exception:  # noqa: BLE001
        return ""


def _mentions(segment: str, endpoint: str) -> bool:
    """Is this endpoint in the source as a WHOLE path?

    A plain `in` is not enough and the bite-proof caught it: `/api/ps` is a
    substring of `/api/psx`, so renaming the endpoint passed. The character
    after it must not be a path character."""
    return re.search(re.escape(endpoint) + r"(?![A-Za-z0-9_])", segment) is not None


# ==========================================================================
#   1. the file is there and reads as Python
# ==========================================================================

def t_the_module_is_there_and_parses():
    check(f"backend/jarvis_agent.py is where the loader looks ({AGENT})",
          AGENT.is_file(), "; ".join(missing("jarvis_agent.py")) or "missing")
    tree, text = _parse()
    check("it parses as Python, so every pin below is about real code",
          tree is not None,
          "a file that will not parse is a failure here, never a skip - "
          "nothing can be verified from it")
    if tree is None:
        return
    for name in (TOOLS_FN, SEES_FN, CONTEXT_FN, ALLOWED_FN):
        check(f"the function {name}() is still there", _func(tree, name) is not None,
              f"looked in {AGENT}")


# ==========================================================================
#   2. THE CAPABILITY VOCABULARY - the strings Jarvis recognises
# ==========================================================================

def t_the_tools_capability_is_pinned():
    tree, _text = _parse()
    if tree is None:
        return
    fn = _func(tree, TOOLS_FN)
    if fn is None:
        return
    vocabulary = _vocabulary(fn)
    check(f"{TOOLS_FN}() still decides on the capability {CAPABILITY_TOOLS!r}",
          vocabulary == {CAPABILITY_TOOLS},
          f"it compares the capabilities list against {sorted(vocabulary)}. "
          f"If Ollama renamed the capability, this is the pin to update - and "
          f"the reason the read would have returned None for ever after.")
    check(f"{TOOLS_FN}() reads it from the field {SHOW_FIELD!r}",
          _caps_var(fn) is not None,
          f"no local name is bound from .get({SHOW_FIELD!r}) any more")


def t_the_vision_capability_is_pinned():
    tree, _text = _parse()
    if tree is None:
        return
    fn = _func(tree, SEES_FN)
    if fn is None:
        return
    vocabulary = _vocabulary(fn)
    check(f"{SEES_FN}() still decides on the capability {CAPABILITY_VISION!r}",
          vocabulary == {CAPABILITY_VISION},
          f"it compares the capabilities list against {sorted(vocabulary)}")
    check(f"{SEES_FN}() reads it from the field {SHOW_FIELD!r}",
          _caps_var(fn) is not None)


def t_the_whole_vocabulary_is_exactly_the_pinned_two():
    """So a THIRD capability cannot appear, and a rename cannot pass, without
    this pin being updated on purpose."""
    tree, _text = _parse()
    if tree is None:
        return
    found = set()
    for name in (TOOLS_FN, SEES_FN):
        fn = _func(tree, name)
        if fn is not None:
            found |= _vocabulary(fn)
    check("the capability vocabulary Jarvis recognises is exactly the pinned "
          "{'tools', 'vision'}",
          found == {CAPABILITY_TOOLS, CAPABILITY_VISION},
          f"found {sorted(found)}. A new capability is fine - pin it here, in "
          f"this suite, so the next contract change is noticed too.")


# ==========================================================================
#   3. THE RESPONSE FIELDS - what Jarvis reads, and from where
# ==========================================================================

def t_both_capability_reads_use_api_show():
    tree, text = _parse()
    if tree is None:
        return
    for name in (TOOLS_FN, SEES_FN):
        segment = _segment(tree, text, name)
        check(f"{name}() asks {SHOW_ENDPOINT}",
              _mentions(segment, SHOW_ENDPOINT),
              f"the body no longer mentions {SHOW_ENDPOINT}. Every pin in this "
              f"suite assumes that response shape.")
        check(f"{name}() reads the {SHOW_FIELD!r} field off that response",
              f'"{SHOW_FIELD}"' in segment,
              f"no literal {SHOW_FIELD!r} in the body")


def t_the_context_read_uses_the_pinned_endpoints_and_fields():
    tree, text = _parse()
    if tree is None:
        return
    fn = _func(tree, CONTEXT_FN)
    if fn is None:
        return
    segment = _segment(tree, text, fn.name)
    check(f"{CONTEXT_FN}() asks {PS_ENDPOINT} first", _mentions(segment, PS_ENDPOINT),
          f"no {PS_ENDPOINT} in the body")
    check(f"{CONTEXT_FN}() falls back to {SHOW_ENDPOINT}",
          _mentions(segment, SHOW_ENDPOINT))
    fields = _get_fields(fn)
    missing_fields = [f for f in PS_FIELDS if f not in fields]
    check(f"{CONTEXT_FN}() reads the pinned {PS_ENDPOINT} fields {list(PS_FIELDS)}",
          not missing_fields,
          f"no longer read: {missing_fields}. Found: {sorted(fields)}")
    check(f"{CONTEXT_FN}() reads {SHOW_PARAM_FIELD!r} from {SHOW_ENDPOINT}",
          SHOW_PARAM_FIELD in fields,
          f"found {sorted(fields)}")
    check(f"the {SHOW_PARAM_FIELD} read still matches the {NUM_CTX_RE!r} line",
          NUM_CTX_RE in segment,
          "if Ollama moves how num_ctx is reported, the context length goes "
          "silently back to the default")


def t_api_tags_is_not_part_of_this_contract():
    """Said out loud, because it is easy to assume otherwise: the capability
    reads do NOT use /api/tags. Other modules use it to list the models the PC
    already has (jarvis_chatbot_local, jarvis_hardware, jarvis_work,
    jarvis_second_card, jarvis_screen_picture) - a different question."""
    _tree, text = _parse()
    if text is None:
        return
    check(f"{AGENT.name} does not read /api/tags at all",
          "/api/tags" not in text,
          "it now does, so the note above - and this pin - are out of date. It "
          "is not a failure of the capability contract, but it must be said "
          "which endpoint the contract lives on.")


# ==========================================================================
#   4. NO VERSION GATE - the design decision, kept
# ==========================================================================

def t_no_version_gate_on_the_capability_reads():
    tree, text = _parse()
    if tree is None:
        return
    for name in (TOOLS_FN, SEES_FN):
        segment = _segment(tree, text, name)
        check(f"{name}() does not consult an Ollama VERSION",
              "version" not in segment.lower(),
              "the read is capability-driven on purpose (jarvis_hardware.py:912: "
              "'so a new Ollama version does not forget that a size did not "
              "fit'). A version gate here would make a new Ollama version "
              "forget what the model can do - worse than no guard at all.")


def t_the_three_state_wiring_is_pinned():
    """The two lines that make `None` the SAFE state. Pinned as text: this is
    the documented contract, and changing it changes behaviour."""
    _tree, text = _parse()
    if text is None:
        return
    check("a picture is kept when Ollama did not say "
          f"(`{KEEP_PICTURE_ON_UNKNOWN}`)",
          KEEP_PICTURE_ON_UNKNOWN in text,
          "the call site no longer keeps the picture on None, so an unreadable "
          "capability answer would drop the owner's picture")
    check("tools are removed only on an explicit `is False`",
          TOOLS_REMOVED_ONLY_ON_FALSE in _segment(_tree, text, ALLOWED_FN),
          f"{ALLOWED_FN}() no longer tests `is False`, so None could start "
          f"meanning 'cannot' - the silent regression this suite guards")


# ==========================================================================
#   5. THE THREE STATES, DRIVEN - no Ollama, no socket
# ==========================================================================

@contextlib.contextmanager
def stubbed_show(answer):
    """`_get_json` replaced for one call. `answer` is a dict or an exception."""
    real = AG._get_json
    for cache in (AG._TOOLS_CACHE, AG._SEES_CACHE, AG._CTX_CACHE):
        cache.clear()

    def fake(url, body=None, **kwargs):
        if isinstance(answer, BaseException):
            raise answer
        return answer

    AG._get_json = fake
    try:
        yield
    finally:
        AG._get_json = real
        for cache in (AG._TOOLS_CACHE, AG._SEES_CACHE, AG._CTX_CACHE):
            cache.clear()


def _tools(answer):
    with stubbed_show(answer):
        return AG._model_can_use_tools("http://127.0.0.1:11434", "qwen3:8b")


def _sees(answer):
    with stubbed_show(answer):
        return AG._model_can_see_pictures("http://127.0.0.1:11434", "qwen3:8b")


def t_tools_three_states():
    check("tools: Ollama lists 'tools' -> True",
          _tools({"capabilities": [CAPABILITY_TOOLS]}) is True)
    check("tools: a capabilities list WITHOUT it -> False",
          _tools({"capabilities": [CAPABILITY_VISION]}) is False)
    check("tools: an EMPTY capabilities list -> None, not False (an empty list "
          "is 'it did not say', and False would remove every tool)",
          _tools({"capabilities": []}) is None)
    check("tools: no capabilities key at all -> None",
          _tools({}) is None)
    check("tools: a capabilities value that is NOT a list -> None "
          "(a field-type change must not read as 'cannot')",
          _tools({"capabilities": CAPABILITY_TOOLS}) is None)
    check("tools: a response that raises -> None",
          _tools(RuntimeError("connection refused")) is None)


def t_vision_three_states():
    check("vision: Ollama lists 'vision' -> True",
          _sees({"capabilities": [CAPABILITY_VISION]}) is True)
    check("vision: a capabilities list WITHOUT it -> False",
          _sees({"capabilities": [CAPABILITY_TOOLS]}) is False)
    check("vision: an EMPTY capabilities list -> None, not False",
          _sees({"capabilities": []}) is None)
    check("vision: no capabilities key at all -> None", _sees({}) is None)
    check("vision: a non-list value -> None",
          _sees({"capabilities": 3}) is None)
    check("vision: a response that raises -> None",
          _sees(OSError("no route")) is None)


def t_none_keeps_the_tools():
    """THE SEMANTICS THE WHOLE DESIGN RESTS ON: None means 'offer them anyway'."""
    enabled = list(AG.TOOLS)[:2]
    with stubbed_show({}):
        names, none = AG._allowed_tools(set(enabled), "http://x", "qwen3:8b")
    check("tools: Ollama did not say -> the tools are still offered",
          names == AG.offered_tools(set(enabled)) and bool(names),
          f"got {names!r}")
    check("tools: and it is NOT reported as 'the model itself said none'",
          none is False, f"reported {none!r}")
    with stubbed_show({"capabilities": [CAPABILITY_VISION]}):
        names_false, none_false = AG._allowed_tools(set(enabled), "http://x", "qwen3:8b")
    check("tools: an explicit False DOES remove them, and says so",
          names_false == [] and none_false is True,
          f"got {names_false!r}, {none_false!r}")
    with stubbed_show({"capabilities": [CAPABILITY_TOOLS]}):
        names_true, _none_true = AG._allowed_tools(set(enabled), "http://x", "qwen3:8b")
    check("tools: an explicit True keeps them",
          names_true == AG.offered_tools(set(enabled)), f"got {names_true!r}")


def t_none_keeps_the_picture():
    """Driven through `with_picture_text`, whose contract is "the picture itself
    stays only when keep_picture" - and the call site passes `sees is None`."""
    picture = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    convo = [{"role": "user", "content": [{"type": "text", "text": "what is this?"},
                                          picture]}]

    def cannot_read(_image):
        return {"ok": False, "why": "nothing could be read"}

    sees = _sees({})                       # Ollama did not say -> None
    check("vision: Ollama did not say -> None, so the call site's "
          "`sees is None` is True",
          sees is None, repr(sees))
    kept, _info = AG.with_picture_text(convo, keep_picture=(sees is None),
                                       read=cannot_read)
    check("vision: None therefore KEEPS the picture on the turn",
          any(AG._image_part(p) for p in kept[-1]["content"]),
          f"content={kept[-1]['content']!r}")
    dropped, _info2 = AG.with_picture_text(convo, keep_picture=False,
                                           read=cannot_read)
    check("vision: an explicit False DOES drop it",
          not any(AG._image_part(p) for p in dropped[-1]["content"]),
          f"content={dropped[-1]['content']!r}")
    check("vision: and neither call changes the caller's own list",
          any(AG._image_part(p) for p in convo[-1]["content"]))


def t_a_cache_hit_does_not_coerce_none():
    """The three-state answer is CACHED. A cache that stored `bool(None)` would
    turn 'did not say' into 'cannot' on the second turn of a conversation."""
    with stubbed_show({"capabilities": []}):
        first = AG._model_can_use_tools("http://127.0.0.1:11434", "qwen3:8b")
        second = AG._model_can_use_tools("http://127.0.0.1:11434", "qwen3:8b")
    check("tools: a cached None is still None, not False",
          first is None and second is None, f"{first!r} then {second!r}")
    with stubbed_show({"capabilities": []}):
        first_v = AG._model_can_see_pictures("http://127.0.0.1:11434", "qwen3:8b")
        second_v = AG._model_can_see_pictures("http://127.0.0.1:11434", "qwen3:8b")
    check("vision: a cached None is still None, not False",
          first_v is None and second_v is None, f"{first_v!r} then {second_v!r}")


def t_no_network_was_touched():
    """The two halves are: the file, and a stubbed `_get_json`. Nothing here
    opens a socket, so this suite runs with no Ollama and no network."""
    check("the stub put `_get_json` back",
          AG._get_json is not None and AG._get_json.__name__ != "fake",
          repr(AG._get_json))
    check("no real answer was ever cached",
          not AG._TOOLS_CACHE and not AG._SEES_CACHE and not AG._CTX_CACHE,
          f"{AG._TOOLS_CACHE} {AG._SEES_CACHE} {AG._CTX_CACHE}")


# ==========================================================================
#   main
# ==========================================================================

def main() -> int:
    funcs = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("t_") and callable(fn)]
    for name, fn in funcs:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(f"{name} raised", False,
                  f"{type(exc).__name__}: {exc}\n" + traceback.format_exc())
    print()
    print("PINNED, and where each came from:")
    print(f"  capability strings  {CAPABILITY_TOOLS!r} (jarvis_agent.py:3668), "
          f"{CAPABILITY_VISION!r} (jarvis_agent.py:5742)")
    print(f"  /api/show field     {SHOW_FIELD!r} (jarvis_agent.py:3666, :5740)")
    print(f"  /api/ps fields      {', '.join(PS_FIELDS)} (jarvis_agent.py:3622-3627)")
    print(f"  /api/show fallback  {SHOW_PARAM_FIELD!r} + {NUM_CTX_RE!r} "
          f"(jarvis_agent.py:3632-3635)")
    print(f"  three-state wiring  {KEEP_PICTURE_ON_UNKNOWN!r} (jarvis_agent.py:7721), "
          f"{ALLOWED_FN}() `{TOOLS_REMOVED_ONLY_ON_FALSE}` (jarvis_agent.py:6815)")
    print(f"  NOT part of this    /api/tags is used by other modules to list the "
          f"models on this PC; jarvis_agent.py does not read it.")
    print(f"  NOT verifiable here the 7 ollama/*.go citations at 3133, 3268, 3270, "
          f"3389, 3392, 3447, 6585 - Ollama's source is not in this repository.")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "\n        ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
