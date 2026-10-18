"""test_ollama_contract.py - the Ollama compatibility probe, and the contract it speaks.

    python3 backend/test_ollama_contract.py

WHAT THIS IS, AND WHAT IT IS NOT

`backend/jarvis_ollama_contract.py` is the RUNTIME half of one contract: it asks
the real Ollama `/api/show` at start-up and when the model changes, and sorts the
answer into three outcomes (understood / unknown capabilities / an expected
capability missing). This suite drives it - every case, with no Ollama, no
socket, no console.

`backend/test_ollama_capability_contract.py` on branch
`fix/ollama-capability-contract-guard` (PR #451) is the STATIC half of the SAME
contract: it reads Jarvis's own source and pins the vocabulary, the field name,
the endpoint and the three-state wiring. This suite does not repeat that work.
What it adds is the agreement between the two halves:

  * the probe's `SHOW_ENDPOINT`, `SHOW_FIELD` and vocabulary are pinned AGAINST
    `jarvis_agent.py` and `jarvis_thinking.py` by reading them (test 2 and 3), so
    a rename on either side fails here;
  * `t_the_static_guard_agrees_when_it_is_here` reads PR #451's own constants and
    fails if they and this module's disagree - the moment that branch lands. In
    this tree that file is not on main yet, so it is reported as SKIPPED. A skip
    is not a pass, and the summary below counts it separately.

WHAT IS PROVEN BY BEHAVIOUR, NOT BY READING THE SOURCE

  * the three outcomes, including that a MISSING expected capability is reported
    flatly (test 7) and that a complete list is understood (test 8);
  * that an unknown name is NEWS, not an error, and is surfaced ONCE (test 9);
  * that "Ollama did not answer" is never a pass (test 10);
  * that the evidence stays conservative, so the probe cannot invent a false
    alarm (test 11);
  * that NO VERSION IS READ OR COMPARED, proved twice: the source holds no
    version comparison at all, and two answers that differ ONLY in a
    version-shaped value classify identically (tests 12 and 13). This is the
    design `jarvis_hardware.py` states - "a new Ollama version does not
    forget that a size did not fit";
  * that the probe asks one read-only endpoint, writes nothing and (with `ask`
    injected) never touches the network (test 14).

THE RUNNER IS CHECKED TOO. Every `t_` function lives in the hand-listed `TESTS`
tuple at the bottom, and `t_every_t_function_is_in_the_runner` fails if the two
ever disagree in either direction - an unregistered `t_` function is dead code
that prints green, which is a trap this project has already been bitten by.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import BACKEND, missing  # noqa: E402

import jarvis_ollama_contract as OC  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print("skip  " + why)


# ==========================================================================
#   Reading source, so a pin comes from the code rather than a second copy
# ==========================================================================

MODULE = BACKEND / "jarvis_ollama_contract.py"
AGENT = BACKEND / "jarvis_agent.py"
THINKING = BACKEND / "jarvis_thinking.py"
HARDWARE = BACKEND / "jarvis_hardware.py"
STATIC_GUARD = BACKEND / "test_ollama_capability_contract.py"

_TOOLS_FN = "_model_can_use_tools"
_SEES_FN = "_model_can_see_pictures"
_ALLOWED_FN = "_allowed_tools"
_THINKING_FN = "supports_thinking"


def _parse(path: Path):
    """(the AST, the text) - or (None, None) when the file is not readable."""
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return ast.parse(text), text
    except SyntaxError:
        return None, text


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _segment(tree, text, name):
    fn = _func(tree, name)
    if fn is None:
        return ""
    try:
        return ast.get_source_segment(text, fn) or ""
    except Exception:                                       # noqa: BLE001
        return ""


def _caps_var(fn):
    """The local name bound from `.get("capabilities")` in a function, or None.

    Taken from PR #451's own guard - the technique that ties a vocabulary pin to
    the FIELD, so a function that stopped reading `capabilities` has no such
    name and reads as empty rather than passing over nothing.
    """
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get" and node.value.args):
            continue
        first = node.value.args[0]
        if isinstance(first, ast.Constant) and first.value == "capabilities":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    return target.id
    return None


def _vocabulary(fn):
    """The string literals this function compares the capabilities list against.

    Also PR #451's technique, unchanged: the pin is the comparison, not a grep.
    """
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


def _mentions(segment: str, endpoint: str) -> bool:
    """Is this endpoint in the source as a WHOLE path?

    A plain `in` is not enough and PR #451's own bite-proof caught it: `/api/ps`
    is a substring of `/api/psx`, so a rename passed. The character after the
    endpoint must not be a path character.
    """
    return re.search(re.escape(endpoint) + r"(?![A-Za-z0-9_])", segment) is not None


def _module_constant(tree, name):
    """A module-level `NAME = <literal>` assignment, read as a literal."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:                       # noqa: BLE001
                        return None
    return None


def _fetches_version(node) -> bool:
    """Does this expression read a "version" key ANYWHERE inside it?

    Deliberately not just a direct `.get("version")` chain: a version fetched
    into a name first and then compared - `v = str(show.get("version"))`, an
    `if/else` expression, an f-string - is the same version comparison with the
    word moved away from the `if`. The whole expression is searched, so the name
    is still recognisable as a version when the comparison is read later.
    """
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "get" and sub.args):
            first = sub.args[0]
            if isinstance(first, ast.Constant) and str(first.value).lower() == "version":
                return True
        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant):
            if str(sub.slice.value).lower() == "version":
                return True
    return False


def _version_names(tree):
    """Local names bound from a "version" key anywhere in the module.

    The static half of "no version is compared": a comparison whose operands
    mention one of these names is a version comparison even when the word
    "version" is nowhere near the `if`.
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if _fetches_version(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _version_comparisons(tree, text):
    """Every comparison in the module that touches a version, as source lines.

    Two ways in, because a version comparison can be written two ways: the word
    can be right there in the comparison, or it can be fetched into a name first.
    """
    names = _version_names(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        try:
            segment = ast.get_source_segment(text, node) or ""
        except Exception:                                   # noqa: BLE001
            segment = ""
        operands = [node.left] + list(node.comparators)
        hit = "version" in segment.lower()
        if not hit:
            for side in operands:
                if isinstance(side, ast.Name) and side.id in names:
                    hit = True
        if hit:
            found.append(segment.replace("\n", " ").strip())
    return found


def _version_reads(tree):
    """.get("version") / ["version"] call sites, wherever they are."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and str(first.value).lower() == "version":
                out.append(f".get({first.value!r})")
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and str(node.slice.value).lower() == "version":
            out.append(f"[{node.slice.value!r}]")
    return out


def _imported_top_levels(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _docstring_ids(tree) -> set:
    """The `id()` of every docstring Constant in the module."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", []) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                found.add(id(body[0].value))
    return found


def _code_strings(tree) -> list:
    """Every string literal in the module that is NOT a docstring.

    A guard against "this endpoint is never asked" has to read the CODE, not the
    prose. The module's own docstring names the version endpoint in order to say
    it is never read; searching the whole file would make that sentence trip the
    check and force the docstring to be less clear. So prose is excluded, on
    purpose, and the endpoint can only be found where it would be executed.
    """
    docs = _docstring_ids(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docs]


def _code_mentions(strings, endpoint: str) -> bool:
    return any(_mentions(value, endpoint) for value in strings)


def _calls_named(tree, *names) -> list:
    """Source positions of calls to a bare name (e.g. `open(...)`)."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in names:
            found.append(f"{node.func.id}() at line {node.lineno}")
    return found


def _attributes_named(tree, *names) -> list:
    """Source positions of attribute uses (e.g. `.write_text`, `os.system`)."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in names:
            found.append(f".{node.attr} at line {node.lineno}")
    return found


# ==========================================================================
#   1. the module itself
# ==========================================================================

def t_the_module_is_there_and_parses():
    check(f"backend/jarvis_ollama_contract.py is where the loader looks ({MODULE})",
          MODULE.is_file(), "; ".join(missing("jarvis_ollama_contract.py"))
          or f"missing from {BACKEND}")
    tree, _text = _parse(MODULE)
    check("it parses as Python, so every pin below is about real code",
          tree is not None,
          "a file that will not parse is a failure here, never a skip - nothing "
          "can be verified from it")
    for name in ("probe", "classify", "text", "forget", "Report"):
        check(f"the module still offers {name}()", hasattr(OC, name),
              f"looked in {MODULE}")


def t_the_three_outcomes_are_exactly_three():
    check("there are exactly three verdicts, and they are the pinned ones",
          tuple(OC.VERDICTS) == (OC.UNDERSTOOD, OC.UNKNOWN_CAPABILITIES,
                                 OC.MISSING_EXPECTED)
          and len(OC.VERDICTS) == 3,
          f"VERDICTS is {OC.VERDICTS!r}")
    check("the three verdict strings are distinct",
          len(set(OC.VERDICTS)) == 3, f"{OC.VERDICTS!r}")
    check("the module says, in ITS OWN source, that the three are the contract",
          "the three outcomes" in MODULE.read_text(encoding="utf-8", errors="replace").lower(),
          "the docstring no longer names the three outcomes")


# ==========================================================================
#   2. the endpoint and the field - pinned against the reader, not restated
# ==========================================================================

def t_the_endpoint_and_field_are_the_ones_jarvis_uses():
    tree, text = _parse(AGENT)
    if tree is None:
        skip(f"{AGENT} is not readable here, so the endpoint pin cannot be "
             f"taken from the reader. {missing('jarvis_agent.py')}")
        return
    for fn_name in (_TOOLS_FN, _SEES_FN):
        segment = _segment(tree, text, fn_name)
        check(f"{fn_name}() in jarvis_agent.py still asks {OC.SHOW_ENDPOINT}",
              _mentions(segment, OC.SHOW_ENDPOINT),
              f"the body no longer mentions {OC.SHOW_ENDPOINT}")
        check(f"{fn_name}() still reads the {OC.SHOW_FIELD!r} field",
              _caps_var(_func(tree, fn_name)) is not None,
              f"no local name is bound from .get({OC.SHOW_FIELD!r}) any more")
    check(f"the probe's own endpoint is the reader's ({OC.SHOW_ENDPOINT!r})",
          OC.SHOW_ENDPOINT == "/api/show", repr(OC.SHOW_ENDPOINT))
    check(f"the probe's own field is the reader's ({OC.SHOW_FIELD!r})",
          OC.SHOW_FIELD == "capabilities", repr(OC.SHOW_FIELD))


def t_the_vocabulary_matches_what_jarvis_reads():
    tree, _text = _parse(AGENT)
    if tree is None:
        skip(f"{AGENT} is not readable here, so the vocabulary pin cannot be "
             f"taken from the reader. {missing('jarvis_agent.py')}")
        return
    found = set()
    for fn_name in (_TOOLS_FN, _SEES_FN):
        fn = _func(tree, fn_name)
        if fn is not None:
            found |= _vocabulary(fn)
    check("jarvis_agent.py's two capability reads name exactly the capabilities "
          "the probe expects from a model",
          found == {"tools", "vision"},
          f"jarvis_agent.py compares against {sorted(found)}")
    check("... and every one of those is in the probe's JARVIS_USES",
          found <= set(OC.JARVIS_USES),
          f"the probe would not notice {sorted(found - set(OC.JARVIS_USES))} "
          f"going quiet. JARVIS_USES is {OC.JARVIS_USES!r}")

    thinking_tree, _t2 = _parse(THINKING)
    if thinking_tree is None:
        skip(f"{missing('jarvis_thinking.py')} - the thinking half of the "
             f"vocabulary cannot be pinned from its reader in this tree")
    else:
        fn = _func(thinking_tree, _THINKING_FN)
        check(f"jarvis_thinking.py's {_THINKING_FN}() still exists",
              fn is not None)
        if fn is not None:
            segment = ast.get_source_segment(
                THINKING.read_text(encoding="utf-8", errors="replace"), fn) or ""
            check("... and it still decides on 'thinking', the third name the "
                  "probe expects",
                  '"thinking"' in segment or "'thinking'" in segment,
                  "if it renamed the capability, the probe expects a name "
                  "nothing reads any more")
            check("... and 'thinking' is in the probe's JARVIS_USES",
                  "thinking" in OC.JARVIS_USES, repr(OC.JARVIS_USES))


def t_the_static_guard_agrees_when_it_is_here():
    """PR #451's guard pins the same literals from the reader's side. When it is
    on this branch, the two pins must be the same pin.

    In this tree it is not on main yet, so this is a SKIP - counted separately in
    the summary, never as a pass.
    """
    if not STATIC_GUARD.is_file():
        skip("PR #451's static guard (backend/test_ollama_capability_contract.py) "
             "is not on this branch yet, so the two pins cannot be compared - "
             "this is NOT a pass, and it must be re-run once #451 lands")
        return
    tree, _text = _parse(STATIC_GUARD)
    check("PR #451's guard parses", tree is not None, str(STATIC_GUARD))
    if tree is None:
        return
    for name, ours in (("CAPABILITY_TOOLS", OC.JARVIS_USES[0]),
                       ("CAPABILITY_VISION", OC.JARVIS_USES[1]),
                       ("SHOW_FIELD", OC.SHOW_FIELD)):
        theirs = _module_constant(tree, name)
        check(f"PR #451's {name} is this module's {ours!r}",
              theirs == ours,
              f"#451 pins {theirs!r}, jarvis_ollama_contract.py uses {ours!r} - "
              f"one of the two is now wrong, and a disagreement between the two "
              f"halves of one contract is worse than either alone")


# ==========================================================================
#   3. reading the answer - the rule, and the three states
# ==========================================================================

def t_the_answer_rule_matches_jarvis_agents_own():
    """The probe must call an absent field, a non-list and an EMPTY list by the
    same name jarvis_agent.py does: "Ollama did not say"."""
    tree, text = _parse(AGENT)
    if tree is None:
        skip(f"{AGENT} is not readable, so the reader's rule cannot be compared")
    else:
        for fn_name in (_TOOLS_FN, _SEES_FN):
            fn = _func(tree, fn_name)
            segment = ast.get_source_segment(text, fn) if fn is not None else ""
            segment = segment or ""
            var = _caps_var(fn) if fn is not None else None
            guards = sorted(set(re.findall(r"isinstance\(\w+, \w+\)", segment)))
            check(f"{fn_name}() treats a list AND non-empty as the only usable "
                  f"answer (`isinstance(caps, list) and caps`)",
                  bool(segment) and var is not None
                  and f"isinstance({var}, list)" in segment
                  and f"and {var}" in segment,
                  f"the reader's own guard changed: {guards}")

    module_text = MODULE.read_text(encoding="utf-8", errors="replace")
    check("the probe spells that same rule for its own read "
          "(`isinstance(caps, list) and caps`)",
          "isinstance(caps, list) and caps" in module_text,
          "the probe's own guard changed; a mismatch here is how an EMPTY list "
          "starts reading as 'cannot', which removes every tool")

    cases = [
        ({"capabilities": ["tools"]}, ("tools",), "a one-name list reads through"),
        ({"capabilities": ["Tools", " tools "]}, ("tools",),
         "names are lowercased and de-duplicated, so a case change is not a "
         "second capability"),
        ({"capabilities": []}, None, "an EMPTY list is 'did not say', not 'cannot'"),
        ({}, None, "no capabilities key at all is 'did not say'"),
        ({"capabilities": "tools"}, None, "a non-list value is 'did not say'"),
        ({"capabilities": 3}, None, "a number is 'did not say'"),
        ({"capabilities": [""]}, None, "a list of blanks is 'did not say'"),
        (None, None, "no answer at all is 'did not say'"),
        ("not a dict", None, "a body that is not an object is 'did not say'"),
    ]
    for body, want, why in cases:
        got = OC.classify(body, model="m").said
        check(f"said: {why}", got == want, f"expected {want!r}, got {got!r}")


def t_only_the_three_verdicts_ever_come_out():
    """A table wide enough that all three outcomes appear in it, so this is not
    a vacuous check."""
    answers = [
        {"capabilities": ["completion", "tools", "vision", "thinking"]},
        {"capabilities": ["completion", "tools", "audio"]},
        {"capabilities": ["completion"], "model_info": {"clip.has_vision_encoder": True}},
        {"capabilities": ["completion"], "template": "{{ if .Tools }}"},
        {"capabilities": ["completion"], "template": "{% if enable_thinking %}"},
        {"capabilities": ["completion"], "projector_info": {"clip": {"vision": True}}},
        {"capabilities": []},
        {},
        None,
        {"capabilities": ["completion"]},
        {"capabilities": ["completion", "thinking"]},
    ]
    seen = set()
    bad = []
    for answer in answers:
        got = OC.classify(answer, model="m").verdict
        if got is not None and got not in OC.VERDICTS:
            bad.append(got)
        seen.add(got)
    check("no answer can produce a verdict outside the pinned three",
          not bad, f"got {bad!r}")
    check("the table produces all three outcomes (and the honest 'did not say')",
          {OC.UNDERSTOOD, OC.UNKNOWN_CAPABILITIES, OC.MISSING_EXPECTED} <= seen
          and None in seen,
          f"the table only produced {sorted(str(v) for v in seen)}")


# ==========================================================================
#   4. the outcomes, driven
# ==========================================================================

def t_missing_expected_is_reported_flatly():
    cases = [
        ({"capabilities": ["completion"],
          "model_info": {"clip.has_vision_encoder": True}},
         ("vision",), "a model_info key names a vision encoder"),
        ({"capabilities": ["completion"],
          "model_info": {"clip.vision.image_size": 336}},
         ("vision",), "a clip.vision model_info key"),
        ({"capabilities": ["completion"], "projector_info": {"clip": {}}},
         ("vision",), "a projector is attached"),
        ({"capabilities": ["completion"], "template": "{{ if .Tools }}..{{ end }}"},
         ("tools",), "the chat template branches on .Tools"),
        ({"capabilities": ["completion"], "modelfile": "TEMPLATE tool_call"},
         ("tools",), "the Modelfile mentions tool_call"),
        ({"capabilities": ["completion"], "template": "{% if enable_thinking %}"},
         ("thinking",), "the chat template branches on enable_thinking"),
    ]
    for answer, want, why in cases:
        report = OC.classify(answer, model="m")
        check(f"MISSING: {why} -> {want[0]!r} is reported",
              report.verdict == OC.MISSING_EXPECTED and report.missing == want,
              f"verdict={report.verdict!r} missing={report.missing!r}")
        check(f"MISSING: ... and the sentence says the model is about to be "
              f"under-used",
              "under-use" in report.note,
              f"note={report.note!r}")
        check(f"MISSING: ... and the missing name is in the sentence",
              want[0] in report.note, f"note={report.note!r}")

    both = {"capabilities": ["completion"],
            "model_info": {"clip.has_vision_encoder": True},
            "template": "{{ if .Tools }}"}
    report = OC.classify(both, model="m")
    check("MISSING: two missing at once are both named, in a stable order",
          report.missing == ("tools", "vision"),
          f"missing={report.missing!r}")

    no_list = OC.classify({"model_info": {"clip.vision.patch_size": 14}}, model="m")
    check("MISSING: an ABSENT list beside plain evidence is still a missing "
          "expected capability - that is the renamed-field case",
          no_list.verdict == OC.MISSING_EXPECTED and no_list.missing == ("vision",),
          f"verdict={no_list.verdict!r} missing={no_list.missing!r}")

    all_known = OC.classify(
        {"capabilities": ["completion", "tools", "vision", "thinking"],
         "model_info": {"clip.has_vision_encoder": True},
         "template": "{{ if .Tools }}"}, model="m")
    check("MISSING: a capability that IS listed is never called missing, even "
          "when the evidence is there too",
          all_known.verdict == OC.UNDERSTOOD and all_known.missing == (),
          f"verdict={all_known.verdict!r} missing={all_known.missing!r}")


def t_a_complete_list_is_understood():
    report = OC.classify({"capabilities": ["completion", "tools", "vision",
                                           "thinking"]}, model="m")
    check("UNDERSTOOD: a list Jarvis fully knows, with nothing absent",
          report.verdict == OC.UNDERSTOOD, f"verdict={report.verdict!r}")
    check("UNDERSTOOD: nothing unknown and nothing missing are reported",
          report.unknown == () and report.missing == (),
          f"unknown={report.unknown!r} missing={report.missing!r}")
    check("UNDERSTOOD: the sentence names what Ollama listed",
          "tools" in report.note and "vision" in report.note, f"note={report.note!r}")
    check("UNDERSTOOD: it does not ask to be surfaced",
          report.needs_saying is False, repr(report.needs_saying))
    check("UNDERSTOOD: the report says Ollama did answer",
          report.usable is True, repr(report.usable))


def t_unknown_capabilities_are_news_not_an_error():
    report = OC.classify({"capabilities": ["completion", "tools", "audio"]}, model="m")
    check("UNKNOWN: a name Jarvis has never heard of is reported as news",
          report.verdict == OC.UNKNOWN_CAPABILITIES, f"verdict={report.verdict!r}")
    check("UNKNOWN: only the new name is named, not the ones Jarvis knows",
          report.unknown == ("audio",), f"unknown={report.unknown!r}")
    check("UNKNOWN: the sentence says it is not an error",
          "not an error" in report.note, f"note={report.note!r}")
    check("UNKNOWN: nothing is called missing because a name was unfamiliar",
          report.missing == (), f"missing={report.missing!r}")
    check("UNKNOWN: 'completion' is never news - it is on every model",
          "completion" not in OC.classify(
              {"capabilities": ["completion"]}, model="m").unknown,
          f"KNOWN_CAPABILITIES is {OC.KNOWN_CAPABILITIES!r}")

    # .. and it is surfaced ONCE, which is the whole of what "once" means here.
    OC.forget()
    lines = []
    answer = {"capabilities": ["completion", "audio"]}
    ask = lambda _url, _model: answer                            # noqa: E731
    first = OC.probe("qwen3:8b", "http://x", ask=ask, log=lines.append,
                     when="startup")
    second = OC.probe("qwen3:8b", "http://x", ask=ask, log=lines.append,
                      when="model changed")
    check("UNKNOWN: the first time is logged", len(lines) == 1, f"{lines!r}")
    check("UNKNOWN: the second time is NOT logged again - surfaced once",
          len(lines) == 1, f"{lines!r}")
    check("UNKNOWN: ... and the second answer is still the same finding, only "
          "the logging is once",
          first.verdict == second.verdict == OC.UNKNOWN_CAPABILITIES,
          f"{first.verdict!r} then {second.verdict!r}")
    check("UNKNOWN: the log line names the module, the model and the note",
          lines and lines[0].startswith("jarvis_ollama_contract:")
          and "qwen3:8b" in lines[0] and "audio" in lines[0],
          f"{lines!r}")
    third = OC.probe("llama3:8b", "http://x", ask=ask, log=lines.append,
                     when="model changed")
    check("UNKNOWN: a DIFFERENT model is a new finding, and gets its own line",
          len(lines) == 2 and third.model == "llama3:8b", f"{lines!r}")
    OC.forget()
    OC.probe("qwen3:8b", "http://x", ask=ask, log=lines.append)
    check("UNKNOWN: forget() lets the same finding be surfaced once more",
          len(lines) == 3, f"{lines!r}")
    OC.forget()


def t_ollama_did_not_answer_is_never_a_pass():
    for why, ask in (
        ("the connection is refused", lambda _u, _m: None),
        ("the request raises", lambda _u, _m: (_ for _ in ()).throw(OSError("no route"))),
        ("the body is not an object", lambda _u, _m: "html, not JSON"),
    ):
        OC.forget()
        lines = []
        report = OC.probe("m", "http://x", ask=ask, log=lines.append)
        check(f"DID NOT SAY: {why} is reported as NO verdict, never as understood",
              report.verdict is None and report.verdict != OC.UNDERSTOOD,
              f"verdict={report.verdict!r}")
        check(f"DID NOT SAY: {why} says plainly it is not a pass",
              "NOT a pass" in report.note, f"note={report.note!r}")
        check(f"DID NOT SAY: {why} still asks to be surfaced - silence is the "
              f"bug this probe exists for", report.needs_saying is True)
        check(f"DID NOT SAY: {why} is logged once", len(lines) == 1, f"{lines!r}")
    OC.forget()


def t_the_evidence_is_conservative():
    """A missed detection leaves the probe quiet. A WRONG detection tells the
    owner their model is being under-used when it is not. The probe must prefer
    the first."""
    quiet = [
        ({"capabilities": ["completion"],
          "model_info": {"general.architecture": "llama",
                         "llama.context_length": 8192}},
         "model_info keys the probe does not know"),
        ({"capabilities": ["completion"],
          "model_info": {"some.future.encoder": True}},
         "a future encoder key the probe does not know"),
        ({"capabilities": ["completion"],
          "template": "You may not use tools unless asked."},
         "the WORD 'tools' in a template's prose is not evidence"),
        ({"capabilities": ["completion"],
          "template": "Describe what you see with vision."},
         "the WORD 'vision' in a template's prose is not evidence"),
        ({"capabilities": ["completion"], "modelfile": "PARAMETER temperature 0.7"},
         "a Modelfile with no capability branch"),
    ]
    for answer, why in quiet:
        report = OC.classify(answer, model="m")
        check(f"CONSERVATIVE: {why} raises no alarm",
              report.verdict == OC.UNDERSTOOD and report.missing == (),
              f"verdict={report.verdict!r} missing={report.missing!r} "
              f"note={report.note!r}")


# ==========================================================================
#   5. no version gate - the design decision, kept
# ==========================================================================

def t_no_version_is_read_or_compared():
    tree, text = _parse(MODULE)
    check("the module parses, so its own comparisons can be read",
          tree is not None, str(MODULE))
    if tree is None:
        return
    strings = _code_strings(tree)

    check(f"the module never asks /api/version",
          not _code_mentions(strings, "/api/version"),
          "reading Ollama's version at all is the first step towards branching "
          "on it")
    reads = _version_reads(tree)
    check("the module reads no version-shaped field",
          not reads, f"found {reads!r}")
    compared = _version_comparisons(tree, text)
    check("the module holds NO comparison that touches a version - including "
          "one fetched into a name first",
          not compared, f"found {compared!r}")

    base = {"capabilities": ["completion"],
            "model_info": {"clip.has_vision_encoder": True}}
    older = dict(base, version="0.1.0")
    newer = dict(base, version="99.9.9")
    other = dict(base, ollama_version="99.9.9", api_version="7")
    first = OC.classify(older, model="m")
    second = OC.classify(newer, model="m")
    third = OC.classify(other, model="m")
    check("BEHAVIOUR: the same answer under two version-shaped values gets the "
          "same verdict",
          first.verdict == second.verdict == OC.MISSING_EXPECTED,
          f"{first.verdict!r} vs {second.verdict!r}")
    check("BEHAVIOUR: ... and the same missing set",
          first.missing == second.missing == ("vision",),
          f"{first.missing!r} vs {second.missing!r}")
    check("BEHAVIOUR: ... and the same sentence",
          first.note == second.note, f"{first.note!r} vs {second.note!r}")
    check("BEHAVIOUR: a differently-named version field changes nothing either",
          third.verdict == first.verdict and third.note == first.note
          and third.missing == first.missing,
          f"{third.verdict!r} / {third.missing!r}")


#: The sentence in `jarvis_hardware.py` this design rests on. Asserted by its
#: WORDS, never by its line number - a line number is a fact about how much code
#: sits above it, and this project has had four line pins break for that reason.
RULE_SENTENCE = "a new Ollama version does not forget"


def t_a_new_version_does_not_forget_what_a_model_can_do():
    """The rule itself, pinned by its WORDS, not by its line number.

    This used to read `jarvis_hardware.py:952` and assert `lines[951]`. A line
    number is not a property of anything - it is a fact about how much code
    happens to sit above it - so #525 inserting a function higher in the file
    moved the sentence down and turned three checks red on a tree where nothing
    was wrong. That is the same failure as `origin/main`'s copy of a file and
    the checkout's own topology: a test measuring the weather.

    A line pin in this project has now broken four times. A sentence that must
    exist, asserted anywhere in the file, breaks for exactly one reason: the
    sentence is gone.
    """
    if not HARDWARE.is_file():
        skip(f"{missing('jarvis_hardware.py')} - the citation cannot be checked")
    else:
        # WHITESPACE-NORMALISED, both sides. The sentence WRAPS in both files,
        # and comparing the raw text fails on a line break that is not a change
        # of meaning - the same class of mistake as the line number this test
        # used to pin. `split()` alone would need the exact spacing; a sentence
        # is a sentence however it is wrapped.
        flat = " ".join(HARDWARE.read_text(encoding="utf-8",
                                           errors="replace").split())
        check("jarvis_hardware.py still carries the sentence that this design "
              "rests on",
              RULE_SENTENCE in flat,
              "the sentence is gone from jarvis_hardware.py")
        probe = " ".join(MODULE.read_text(encoding="utf-8",
                                         errors="replace").split())
        check("... and the probe's own docstring cites where it comes from, so "
              "the reasoning travels with the code",
              "jarvis_hardware.py" in probe and RULE_SENTENCE in probe,
              "the citation was dropped from jarvis_ollama_contract.py")

    low = {"capabilities": ["completion"], "version": "0.1.0",
           "model_info": {"clip.has_vision_encoder": True}}
    high = {"capabilities": ["completion"], "version": "99.9.9",
            "model_info": {"clip.has_vision_encoder": True}}
    check("a new Ollama version does not make Jarvis forget that the model can "
          "see pictures",
          OC.classify(low, model="m").missing == OC.classify(high, model="m").missing
          == ("vision",),
          "the two versions disagreed about what the model can do")


# ==========================================================================
#   6. it only reads, and it writes nothing
# ==========================================================================

def t_the_probe_only_reads_api_show():
    tree, _text = _parse(MODULE)
    check("the module parses, so what it asks can be read", tree is not None,
          str(MODULE))
    if tree is None:
        return
    strings = _code_strings(tree)

    check(f"the probe asks {OC.SHOW_ENDPOINT}",
          _code_mentions(strings, OC.SHOW_ENDPOINT))
    for endpoint in ("/api/generate", "/api/chat", "/api/pull", "/api/delete",
                     "/api/create", "/api/copy", "/api/embed", "/api/ps",
                     "/api/tags", "/api/version"):
        check(f"the probe never asks {endpoint}",
              not _code_mentions(strings, endpoint),
              "a capability probe must not load, pull or unload anything - "
              "/api/generate is a load")

    opens = _calls_named(tree, "open")
    check("the probe opens no file of its own", not opens,
          f"a read-only probe that opens a file is a probe that can write one: "
          f"{opens}")
    writes = _attributes_named(tree, "write_text", "write_bytes", "system",
                              "Popen", "run")
    check("the probe writes no file and starts nothing", not writes, f"{writes}")

    allowed = {"json", "os", "sys", "threading", "urllib", "dataclasses",
               "typing", "__future__"}
    imported = _imported_top_levels(tree)
    check("the probe needs nothing but the standard library",
          imported <= allowed, f"also imports {sorted(imported - allowed)}")
    check("... and not one of them is a child-process or database module",
          not (imported & {"subprocess", "sqlite3", "shutil", "socket",
                           "http", "requests"}),
          f"imports {sorted(imported)}")

    # .. and with `ask` injected it does not reach the network at all.
    import urllib.request
    real = urllib.request.urlopen

    def bomb(*_a, **_k):
        raise AssertionError("the probe opened the network with `ask` injected")

    urllib.request.urlopen = bomb
    try:
        OC.forget()
        report = OC.probe("m", "http://x", ask=lambda _u, _m: {"capabilities": ["completion"]},
                          log=lambda _line: None)
        check("with `ask` injected, no socket is touched",
              report.verdict == OC.UNDERSTOOD, f"verdict={report.verdict!r}")
    except AssertionError as exc:
        check("with `ask` injected, no socket is touched", False, str(exc))
    finally:
        urllib.request.urlopen = real
        OC.forget()


def t_the_report_is_a_plain_sentence():
    missing_report = OC.classify(
        {"capabilities": ["completion"], "model_info": {"clip.has_vision_encoder": True}},
        model="qwen3:8b")
    line = OC.text(missing_report)
    check("the sentence names the model it is about",
          line.startswith("qwen3:8b: "), f"{line!r}")
    check("the sentence says plainly that Jarvis will under-use the model",
          "under-use" in line, f"{line!r}")
    check("the sentence names the capability that is being missed",
          "vision" in line, f"{line!r}")

    unknown_report = OC.classify({"capabilities": ["completion", "audio"]}, model="m")
    check("the unknown-name sentence says it is not an error",
          "not an error" in OC.text(unknown_report), f"{OC.text(unknown_report)!r}")

    did_not_say = OC.classify({}, model="m")
    check("the 'Ollama did not say' sentence says it is not a pass",
          "NOT a pass" in OC.text(did_not_say), f"{OC.text(did_not_say)!r}")


def t_probe_never_raises_on_a_broken_server():
    for why, ask in (
        ("a body full of junk", lambda _u, _m: {"capabilities": {"not": "a list"},
                                                "model_info": "nope",
                                                "template": 7}),
        ("a list where an object belongs", lambda _u, _m: ["nope"]),
        ("a number", lambda _u, _m: 3),
        ("an exception every time", lambda _u, _m: 1 / 0),
    ):
        try:
            OC.forget()
            report = OC.probe("m", "http://x", ask=ask, log=lambda _l: None)
            ok = isinstance(report, OC.Report)
        except Exception as exc:                            # noqa: BLE001
            ok = False
            report = f"{type(exc).__name__}: {exc}"
        check(f"probe() never raises with {why}", ok, f"{report!r}")
    OC.forget()

    saved = os.environ.get("OLLAMA_HOST")
    try:
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11500/"
        check("with no url given, OLLAMA_HOST is where it asks, trailing slash "
              "and all",
              OC.default_url() == "http://127.0.0.1:11500", OC.default_url())
    finally:
        if saved is None:
            os.environ.pop("OLLAMA_HOST", None)
        else:
            os.environ["OLLAMA_HOST"] = saved
    check("with nothing set, it asks loopback",
          OC.default_url().startswith("http://127.0.0.1:"), OC.default_url())


# ==========================================================================
#   7. the runner itself - no dead test functions
# ==========================================================================

def t_every_t_function_is_in_the_runner():
    """A hand-listed runner tuple that misses a name makes that test dead code
    that prints green. It happened to this project's own regression test, so the
    two lists are compared HERE, in both directions, and this check is itself in
    the tuple."""
    found = {name for name, thing in globals().items()
             if name.startswith("t_") and callable(thing)}
    listed = {fn.__name__ for fn in TESTS}
    check("every t_ function in this file is called by the runner",
          not found - listed,
          f"dead, never-run test functions: {sorted(found - listed)} - add them "
          f"to TESTS at the bottom")
    check("the runner names nothing that is not a t_ function in this file",
          not listed - found, f"{sorted(listed - found)}")
    check("the runner is not empty", len(TESTS) >= 10, f"{len(TESTS)} entries")


# ==========================================================================
#   main
# ==========================================================================

TESTS = (
    t_the_module_is_there_and_parses,
    t_the_three_outcomes_are_exactly_three,
    t_the_endpoint_and_field_are_the_ones_jarvis_uses,
    t_the_vocabulary_matches_what_jarvis_reads,
    t_the_static_guard_agrees_when_it_is_here,
    t_the_answer_rule_matches_jarvis_agents_own,
    t_only_the_three_verdicts_ever_come_out,
    t_missing_expected_is_reported_flatly,
    t_a_complete_list_is_understood,
    t_unknown_capabilities_are_news_not_an_error,
    t_ollama_did_not_answer_is_never_a_pass,
    t_the_evidence_is_conservative,
    t_no_version_is_read_or_compared,
    t_a_new_version_does_not_forget_what_a_model_can_do,
    t_the_probe_only_reads_api_show,
    t_the_report_is_a_plain_sentence,
    t_probe_never_raises_on_a_broken_server,
    t_every_t_function_is_in_the_runner,
)


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            check(f"{fn.__name__} raised", False,
                  f"{type(exc).__name__}: {exc}\n" + traceback.format_exc())
    print()
    print(f"{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped (NOT passes - a skip is an unproven check):")
        for why in SKIPPED:
            print("  - " + why)
    if FAILED:
        print("failed:")
        for name in FAILED:
            print("  - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
