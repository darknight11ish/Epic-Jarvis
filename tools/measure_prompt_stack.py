#!/usr/bin/env python3
"""Measure every block that can stack on one Jarvis turn - from the shipped code.

    py -3 tools/measure_prompt_stack.py                   # the table, in plain words
    py -3 tools/measure_prompt_stack.py --json            # the same numbers, machines
    py -3 tools/measure_prompt_stack.py --context 16384   # what share of another window
    py -3 tools/measure_prompt_stack.py --check           # structural drift only
    py -3 tools/measure_prompt_stack.py --backend DIR     # another backend (tests, live copy)

WHY THIS EXISTS. Review #1 of the 10-Review Playbook (the owner's work order of
2026-10-23, section 1) asked for this file - and its own draft was a piece of
code that added up a table of numbers typed into itself and printed
``PASS: Prompt-stack cognitive load budgets verified`` whatever the tree said.
A checker that asserts its own fixture is worse than no checker: it answers
"is the prompt too big?" with a constant. This one reads the modules that are
actually shipped and measures what they contain, block by block, with the
place each block is built written beside it.

WHAT IT MEASURES, and where each block comes from:

  * the base persona and rules - ``LANE_SYSTEM`` (``jarvis_agent.py:7162``),
    sent first on every local turn by ``with_rules_first`` (``jarvis_agent.py:9207``);
  * the chat-template reserve the real budget holds back -
    ``_TEMPLATE_TOKENS`` (``jarvis_agent.py:7192``);
  * the pinned + recalled memory path - ``PROFILE_LIMIT = 1200`` characters
    (``rebuilt/jarvis_memory.py:4779``) and ``JARVIS_MEMORY_K``, default 5
    recalled facts (``memory-prefix.patch:41``); the recalled facts have **no
    per-fact ceiling**, which is why its row says so;
  * the authorial voiceprint block - ``jarvis_voiceprint.prompt_block``
    (``jarvis_voiceprint.py:630``) and its worst case, ``MAX_TEXT = 4000``
    per exemplar with 3 exemplars (``jarvis_voiceprint.py:493,804``);
  * the tool schemas - the whole catalogue and the same catalogue plus
    ``more_tools`` (``TOOLS`` at ``jarvis_agent.py:2053``, ``more_tools_schema``
    at ``:6520``, ``_schemas_for`` at ``:6977``, summed by the same
    ``estimate_tokens`` ``budget()`` uses at ``:9192``);
  * the eight real per-turn system notes the review's six-block list never
    names: manner, spoken, Live, focus, cut-off, crisis, next-time, outside;
  * two blocks the work order lists that **do not exist in this tree** -
    skills instructions and ``<project_workspace>``. They are printed as
    ``ABSENT IN TREE - not measured``, never as a 0-token pass, because a zero
    is a claim and "not there" is a different claim.

WHAT IT DOES NOT DO: it does not count tokens. There is no tokenizer in this
repository, and the shipped estimator is characters-based: ``estimate_tokens``
is ``len(text)//3`` plus 6 tokens of framing per message (its own docstring,
``jarvis_agent.py:4385-4404``, calls it "pessimistic"). Every number this tool
prints is labelled **estimate**, and the ``chars/4`` column is a second
estimate that disagrees with the first by about a quarter - which is the honest
size of the uncertainty. The only real token counts on this project are the
ones Ollama reports (``prompt_eval_count``, recorded in ``speed.jsonl``).

WHEN A NUMBER IS NOT MEASURABLE. If ``jarvis_agent`` cannot be imported (an
older live backend, a missing dependency), the tool falls back to reading the
source with ``ast`` and says so, loudly, at the top of the output. Only plain
string constants and the ``TOOLS`` keys can be read that way; any block that
needs a function to build is printed as **NOT MEASURED** with the reason,
rather than guessed.

THE TWO ESTIMATE METHODS, named everywhere so they cannot be confused:

    E3   ``estimate_tokens`` - the repository's own: ``chars//3``, plus 6
         tokens a message. Pessimistic by design (English is nearer 4).
    E4   ``chars/4`` - the other common rule of thumb, about a quarter lower.

EXIT CODES

    0   the measurement ran (report mode, ``--json``, or ``--check`` with no drift)
    1   ``--check`` only: structural drift was found
    2   the backend folder or the module could not be read at all - nothing was measured

``--check`` AND WHAT IT WILL NOT DO. The work order asked this tool to enforce
a "two-tier hard token cap" of 3,600 and 4,500 tokens. **Those caps are not
real and this tool does not enforce them.** The 3,800/3,600 figures are the
project's own *measured* ordinary prompt of 2026-10-15 - 3,838 tokens,
``docs/MODEL-TOPOLOGY.md:465`` - rounded down, not a ceiling; a cap there would
have fired on the very turn the project measured and called fine. There is no
tokenizer here to measure a true cap against, and inventing one from
``chars//3`` would be exactly the mistake this file exists to replace. So
``--check`` is a **structural** gate and nothing else:

  * the shipped catalogue's size must equal ``TOOL_COUNT_MEASURED`` below (34
    on 2026-10-23) - a tool added or removed without this tool being re-read
    fails, so a stale table can never quietly "pass". That one is a statement
    about THIS repository's ``backend/``; ``--backend DIR`` on another folder
    (a test fixture, a live install) checks that folder's own comments against
    its own catalogue and prints the recorded count as a note instead;
  * every tool-count claim written in ``jarvis_agent.py``'s own comments must
    equal the catalogue's real size. On 2026-10-23 two of them do not: the
    comment at ``:6121`` says "All 23 tools", and ``:6454`` says "the full
    31-tool list", against 34 shipped. **This is the finding, not a broken
    gate** - F1 in ``docs/REVIEW-1-PROMPT-STACK-MEASURED-2026-10-23.md``, and
    ``.dsh-scratch/DOC2-PROPOSALS/prompt-stack-proposals.md`` carries the
    exact patch. ``--check`` exits 1 today for that reason, and 0 once those
    comments state 34. It is deliberately NOT wired into CI while the finding
    is open: a red gate on a known defect trains people to ignore red.

The tool never writes anything, never talks to Ollama, and never reads the
owner's live config. The one thing it reads from disk is the source under
``backend/``.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BACKEND = REPO / "backend"

#: The catalogue size this tool's recorded numbers were measured against.
#: ``--check`` fails when the shipped catalogue moves without this number and
#: the table in the review doc moving with it.
TOOL_COUNT_MEASURED = 34
TOOL_COUNT_AT = "2026-10-23"

#: The tool-count claims written in ``backend/jarvis_agent.py``'s comments.
#: ``--check`` compares every one it finds with what is really shipped; a claim
#: that has been reworded away is reported as a note, not as drift.
COUNT_CLAIMS = (
    (re.compile(r"All (\d+) tools"), "All <n> tools"),
    (re.compile(r"full (\d+)-tool list"), "full <n>-tool list"),
)

#: The window the tool falls back to when the module has no DEFAULT_CONTEXT.
FALLBACK_CONTEXT = 4096

#: Where the repository disagrees about the everyday lane's window. Printed
#: with the share, so a reader cannot mistake one file's number for a fact.
WINDOW_SOURCES = (
    ("backend/jarvis-primary.Modelfile:119", "num_ctx 16384 - what the model file asks for"),
    ("docs/HARDWARE-PROFILES.md:7", "4,096 - the measured context of the everyday lane"),
    ("backend/jarvis_agent.py:3944", "DEFAULT_CONTEXT = 4096 - the code's own fallback"),
)


# ---------------------------------------------------------------------------
#   Two estimators, named so they cannot be confused
# ---------------------------------------------------------------------------


def message_tokens(chars: int) -> int:
    """``estimate_tokens`` for ONE system message: 6 tokens + ``chars//3``."""
    return 6 + max(0, int(chars)) // 3


def json_tokens(chars: int) -> int:
    """``estimate_tokens`` for a JSON blob: ``chars//3``, no framing."""
    return max(0, int(chars)) // 3


def chars_per_4(chars: int) -> int:
    """The other rule of thumb: ``chars/4``, rounded up. A different estimate."""
    chars = max(0, int(chars))
    return (chars + 3) // 4 if chars else 0


def schemas_tokens(src, schemas) -> int:
    """``estimate_tokens`` over a list of schemas - per schema, as budget() does.

    The shipped estimator adds each dict's ``len(json.dumps(item))//3`` rather
    than dividing one big blob, so the same list costs a few tokens less than
    ``len(json.dumps(list))//3``. Asking the module keeps this row exactly equal
    to ``tool_text_tokens``, which is what ``budget()`` subtracts.
    """
    schemas = list(schemas)
    if src.agent is not None:
        est = getattr(src.agent, "estimate_tokens", None)
        if callable(est):
            try:
                return int(est(schemas))
            except Exception:                                      # noqa: BLE001
                pass
    return sum(json_tokens(len(json.dumps(item, ensure_ascii=False))) for item in schemas)


def schemas_chars(schemas) -> int:
    """The JSON characters of a schema list, counted the way the estimator is."""
    return sum(len(json.dumps(item, ensure_ascii=False)) for item in list(schemas))


# ---------------------------------------------------------------------------
#   Reading the shipped code - by import, or by ast when the import fails
# ---------------------------------------------------------------------------


class Source:
    """The backend folder, imported if it can be and parsed if it cannot."""

    def __init__(self, backend: Path):
        self.backend = Path(backend)
        self.mode = "static"
        self.why = ""
        self.modules: dict = {}
        self.agent = None
        self._files: dict = {}
        for path in (str(self.backend), str(self.backend / "rebuilt")):
            # This folder FIRST, always: measuring a second folder in the same
            # process (the tests do) must not read the first one's modules.
            while path in sys.path:
                sys.path.remove(path)
            sys.path.insert(0, path)
        try:
            self.agent = _import_from("jarvis_agent", self.backend)
            self.modules["jarvis_agent"] = self.agent
            self.mode = "import"
        except Exception as exc:                                   # noqa: BLE001
            self.why = f"{type(exc).__name__}: {exc}"
        if self.mode == "import":
            for name in ("jarvis_manner", "jarvis_live", "jarvis_wellbeing",
                         "jarvis_next_time", "jarvis_voiceprint"):
                try:
                    self.modules[name] = _import_from(name, self.backend)
                except Exception:                                  # noqa: BLE001
                    pass

    # -- raw text ----------------------------------------------------------

    def file_text(self, name: str) -> str:
        """One source file under the backend folder, read once; "" if absent."""
        if name not in self._files:
            try:
                self._files[name] = (self.backend / name).read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                self._files[name] = ""
        return self._files[name]

    def agent_text(self) -> str:
        return self.file_text("jarvis_agent.py")

    # -- values ------------------------------------------------------------

    def const(self, module: str, attr: str, filename: str):
        """A module-level string constant: from the module, else from the source.

        None when it is not there, or when the source computes it instead of
        stating it - a guess here would be worse than "not measured".
        """
        mod = self.modules.get(module)
        if mod is not None:
            value = getattr(mod, attr, None)
            if isinstance(value, str):
                return value
            if value is not None:
                return None
        return static_constant(self.file_text(filename), attr)

    def call(self, module: str, function: str, *args, **kwargs):
        """Call a shipped function, or None when the module did not import."""
        mod = self.modules.get(module)
        func = getattr(mod, function, None) if mod is not None else None
        if not callable(func):
            return None
        try:
            return func(*args, **kwargs)
        except Exception:                                          # noqa: BLE001
            return None

    def tool_names(self) -> list:
        """The shipped catalogue's tool names, in ``TOOLS`` order."""
        if self.agent is not None:
            tools = getattr(self.agent, "TOOLS", None)
            if isinstance(tools, dict):
                return [str(n) for n in tools]
        return static_tool_names(self.agent_text())

    def schemas(self, names) -> list:
        """The schema dicts a request would carry for ``names``.

        Built by the module's own ``_schemas_for`` when it imported (so the
        shipped sanitiser and the ``instead`` handling are the ones measured);
        otherwise by asking each ``Tool`` for its schema, if the objects are
        there; otherwise [] - and the caller prints NOT MEASURED.
        """
        names = list(names)
        if self.agent is not None:
            build = getattr(self.agent, "_schemas_for", None)
            if callable(build):
                try:
                    return list(build(names, [], {}))
                except Exception:                                  # noqa: BLE001
                    pass
            tools = getattr(self.agent, "TOOLS", None)
            if isinstance(tools, dict):
                out = []
                for name in names:
                    tool = tools.get(name)
                    if tool is None:
                        continue
                    try:
                        out.append(tool.schema(names))
                    except Exception:                              # noqa: BLE001
                        return []
                return out
        return []


def _import_from(name: str, backend: Path):
    """Import ``name`` from ``backend``, never a copy cached from another folder.

    The tests measure a fixture folder and the real one in the same process; a
    plain ``import`` would hand the second call the first folder's module out of
    ``sys.modules`` and measure the wrong tree without saying so.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        origin = Path(getattr(cached, "__file__", "") or "").resolve().parent
        if origin != Path(backend).resolve():
            del sys.modules[name]
    return __import__(name)


def _assigned_items(node):
    """``(name, value)`` for a module-level assignment, plain or annotated.

    The shipped ``TOOLS`` is written ``TOOLS: dict = {`` - an AnnAssign, not an
    Assign. A reader that only looked at plain assignments therefore found ZERO
    tools in this module and said so with a straight face; the fallback reads
    both shapes.
    """
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                yield target.id, node.value
    elif (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
          and node.value is not None):
        yield node.target.id, node.value


def _assignments(tree) -> dict:
    """Every module-level name and the expression it is assigned, by name."""
    assigned = {}
    for node in tree.body:
        for target, value in _assigned_items(node):
            assigned[target] = value
    return assigned


def _literal(node, assigned, depth=0):
    """The string a module-level expression really is, or None.

    Only a literal (adjacent literals are one constant in the tree), a ``+`` of
    literals, or another literal name in the same file. Anything computed - a
    format, a comprehension, a call - is None: a fallback that guessed would be
    worse than one that says "not measured".
    """
    if node is None or depth > 6:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left, assigned, depth + 1), _literal(node.right, assigned, depth + 1)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name):
        return _literal(assigned.get(node.id), assigned, depth + 1)
    return None


def static_constant(source: str, name: str):
    """The plain string a module-level ``name`` is assigned, or None."""
    if not source:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    assigned = _assignments(tree)
    return _literal(assigned.get(name), assigned)


def static_tool_names(source: str) -> list:
    """The keys of the module-level ``TOOLS`` dict, read with ast.

    Most keys are written as strings, but five of the shipped catalogue's are
    module constants (``SANDBOX_TOOL:``, ``FILES_TOOL:`` and the like), so a
    reader that took only string keys found 29 of 34. Those names are resolved
    through the file's own assignments; one that still cannot be read becomes
    ``?NAME``, so the COUNT stays right and the table can say what it could not
    read rather than quietly measuring a smaller catalogue.
    """
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    assigned = _assignments(tree)
    for node in tree.body:
        for target, value in _assigned_items(node):
            if target != "TOOLS" or not isinstance(value, ast.Dict):
                continue
            names = []
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.append(key.value)
                elif isinstance(key, ast.Name):
                    resolved = _literal(assigned.get(key.id), assigned)
                    names.append(resolved if isinstance(resolved, str) else f"?{key.id}")
                else:
                    names.append("?<computed key>")
            return names
    return []


# ---------------------------------------------------------------------------
#   The blocks
# ---------------------------------------------------------------------------


def _row(rows, key, label, where, chars=None, e3=None, e4=None, note="",
         when="", absent=False, measured=True):
    """One table row. ``e3``/``e4`` default to the two estimators on ``chars``."""
    if chars is not None:
        e3 = message_tokens(chars) if e3 is None else e3
        e4 = chars_per_4(chars) if e4 is None else e4
    elif e3 is not None:
        e4 = chars_per_4(e3 * 3) if e4 is None else e4
    rows.append({"key": key, "label": label, "where": where,
                 "chars": chars, "e3": e3, "e4": e4, "note": note,
                 "when": when, "absent": absent,
                 "measured": measured and not absent})


def build_rows(src: Source) -> list:
    """Every block, measured. Returned as rows so ``--json`` and the table agree."""
    rows: list = []
    agent_path = "backend/jarvis_agent.py"

    # ---- 1. the persona and the template reserve -------------------------
    lane = src.const("jarvis_agent", "LANE_SYSTEM", "jarvis_agent.py")
    if lane is None:
        _row(rows, "persona", "Base persona + rules (LANE_SYSTEM)",
             f"{agent_path}:7162", note="NOT MEASURED - the constant was not found",
             when="every local turn", measured=False)
    else:
        _row(rows, "persona", "Base persona + rules (LANE_SYSTEM)",
             f"{agent_path}:7162, sent first :9207",
             chars=len(lane), when="every local turn")
    template = None
    if src.agent is not None:
        template = getattr(src.agent, "_TEMPLATE_TOKENS", None)
    persona_e3 = rows[0]["e3"] if rows and rows[0]["measured"] else None
    if isinstance(template, int) and persona_e3 is not None:
        extra = max(0, int(template) - persona_e3)
        _row(rows, "template", "Chat-template reserve (inside _TEMPLATE_TOKENS)",
             f"{agent_path}:7192", chars=None, e3=extra,
             note=f"_TEMPLATE_TOKENS = {template}; budget() subtracts it whole",
             when="every local turn")
    else:
        _row(rows, "template", "Chat-template reserve (_TEMPLATE_TOKENS)",
             f"{agent_path}:7192", chars=None,
             note="NOT MEASURED - needs the imported module", when="every local turn",
             measured=False)

    # ---- 2. memory -------------------------------------------------------
    limit = 1200
    if src.modules.get("jarvis_memory") is None:
        try:
            import jarvis_memory  # noqa: PLC0415 - rebuilt/ copy
            src.modules["jarvis_memory"] = jarvis_memory
        except Exception:                                          # noqa: BLE001
            pass
    memory_mod = src.modules.get("jarvis_memory")
    if memory_mod is not None:
        limit = int(getattr(memory_mod, "PROFILE_LIMIT", limit))
    heading = "Always keep in mind (the owner pinned these):"
    if src.agent is not None:
        heads = getattr(src.agent, "_FACTS_HEADINGS", None)
        if isinstance(heads, (list, tuple)) and heads:
            heading = str(heads[0])
    #: 5 pinned facts at the 240 characters each that fit the limit, plus the heading.
    pinned_chars = len(heading) + 1 + sum(len("- ") + 240 for _ in range(5))
    _row(rows, "pinned", "Pinned facts ('Always keep in mind')",
         "rebuilt/jarvis_memory.py:4779 PROFILE_LIMIT", chars=pinned_chars,
         note=f"CEILING: {limit:,} characters of fact text; 5 x 240 characters shown",
         when="when the owner has pinned facts")
    #: JARVIS_MEMORY_K = 5 recalled facts (memory-prefix.patch:41). Each hit has
    #: no length cap anywhere in backend/ - the row says so rather than invent one.
    hit_chars = len("Recalled for this question:") + 1 + sum(len("- ") + 160 for _ in range(5))
    _row(rows, "recalled", "Recalled facts (top 5)",
         "memory-prefix.patch:41 JARVIS_MEMORY_K=5", chars=hit_chars,
         note="NO CEILING: 5 hits, each one's length is not capped anywhere",
         when="when memory recalls")

    # ---- 3. the voiceprint block ----------------------------------------
    rules = src.call("jarvis_voiceprint", "rules_block")
    max_text = 4000
    if src.modules.get("jarvis_voiceprint") is not None:
        max_text = int(getattr(src.modules["jarvis_voiceprint"], "MAX_TEXT", max_text))
    if isinstance(rules, str):
        typical = len(rules) + 2 + 3 * (len("- ") + 400)
        worst = len(rules) + 2 + 3 * (len("- ") + max_text)
        _row(rows, "voiceprint_typical", "Voiceprint block - 3 x 400-character samples",
             "backend/jarvis_voiceprint.py:630, :493",
             chars=typical, note="synthetic sample length; the block is the owner's own words",
             when="drafting turns only")
        _row(rows, "voiceprint_worst", "Voiceprint block - 3 x 4,000-character samples",
             "backend/jarvis_voiceprint.py:804 MAX_TEXT=4000", chars=worst,
             note="WORST CASE: MAX_TEXT per exemplar, 3 exemplars",
             when="drafting turns only")
    else:
        _row(rows, "voiceprint_typical", "Voiceprint block",
             "backend/jarvis_voiceprint.py:630", note="NOT MEASURED - no import, not statically readable",
             when="drafting turns only", measured=False)

    # ---- 4. the tool schemas --------------------------------------------
    names = src.tool_names()
    all_schemas = src.schemas(names)
    if all_schemas:
        all_chars = schemas_chars(all_schemas)
        _row(rows, "tools_all", "Tool schemas - every tool in the catalogue",
             f"{agent_path}:2053, :6977", chars=all_chars,
             e3=schemas_tokens(src, all_schemas), e4=chars_per_4(all_chars),
             note=f"{len(all_schemas)} schemas; the count budget() subtracts",
             when="every turn with tools on")
        more_schema = None
        if src.agent is not None:
            groups = [g[0] for g in getattr(src.agent, "TOOL_GROUPS", ())]
            build = getattr(src.agent, "more_tools_schema", None)
            if callable(build) and groups:
                try:
                    more_schema = build(groups)
                except Exception:                                  # noqa: BLE001
                    more_schema = None
        if more_schema:
            with_more = list(all_schemas) + [more_schema]
            with_chars = schemas_chars(with_more)
            _row(rows, "tools_more", "Tool schemas + more_tools",
                 f"{agent_path}:6520 more_tools_schema", chars=with_chars,
                 e3=schemas_tokens(src, with_more), e4=chars_per_4(with_chars),
                 note="the long list a short-list or full-list turn sends",
                 when="every turn with tools on")
        core = [n for n in getattr(src.agent, "CORE_TOOLS", ()) if n in names] if src.agent else []
        if core:
            core_schemas = src.schemas(core)
            if core_schemas:
                core_chars = schemas_chars(core_schemas)
                _row(rows, "tools_core", f"Tool schemas - the {len(core)} short-list core tools",
                     f"{agent_path}:6154 CORE_TOOLS", chars=core_chars,
                     e3=schemas_tokens(src, core_schemas), e4=chars_per_4(core_chars),
                     note="what the diet / short list costs on a good turn",
                     when="a question the diet recognises")
        per_tool = []
        for name in names:
            one = src.schemas([name])
            if one:
                per_tool.append((schemas_tokens(src, one), name))
        if len(per_tool) >= 9:
            per_tool.sort()
            cheap = sum(cost for cost, _ in per_tool[:9])
            dear = sum(cost for cost, _ in per_tool[-9:])
            _row(rows, "tools_9cheap", "Tool schemas - the 9 cheapest tools",
                 f"{agent_path}:6602 MAX_STICKY_TOOLS=9", chars=None, e3=cheap,
                 note="the best case of a 9-tool carried list: " + ", ".join(n for _, n in per_tool[:9]),
                 when="a 9-tool sticky list")
            _row(rows, "tools_9dear", "Tool schemas - the 9 dearest tools",
                 f"{agent_path}:6602 MAX_STICKY_TOOLS=9", chars=None, e3=dear,
                 note="the worst case of the same list: " + ", ".join(n for _, n in per_tool[-9:]),
                 when="a 9-tool sticky list")
    else:
        _row(rows, "tools_all", "Tool schemas",
             f"{agent_path}:2053 TOOLS", note="NOT MEASURED - no import, and a schema is built, not written",
             when="every turn with tools on", measured=False)

    # ---- 5. the per-turn system notes ------------------------------------
    manner_warm = src.call("jarvis_manner", "note", "warm", False)
    manner_humor = src.call("jarvis_manner", "note", "warm", True)
    spoken = src.const("jarvis_agent", "SPOKEN_NOTE", "jarvis_agent.py")
    live = src.const("jarvis_live", "MODEL_NOTE", "jarvis_live.py")
    focus = src.const("jarvis_agent", "FOCUS_NOTE", "jarvis_agent.py")
    outside = src.const("jarvis_agent", "OUTSIDE_NOTE", "jarvis_agent.py")
    crisis = src.const("jarvis_wellbeing", "NOTE", "jarvis_wellbeing.py")
    dropped = src.const("jarvis_agent", "DROPPED_PROMPT_NOTE", "jarvis_agent.py")
    cut_off = None
    template_note = src.const("jarvis_agent", "CUT_OFF_NOTE", "jarvis_agent.py")
    cut_max = 240
    if src.agent is not None:
        cut_max = int(getattr(src.agent, "CUT_OFF_MAX", cut_max))
    if isinstance(template_note, str):
        cut_off = template_note.format(said="x" * cut_max)
    next_note = src.call("jarvis_next_time", "note_text",
                         [{"about": "the dentist", "text": "ask whether it was booked",
                           "created": 0}], 0)

    notes = (
        ("manner", "Manner line (warm, default)", "backend/jarvis_manner.py:110, added at :7914",
         manner_warm, "warm / plain; the humour switch adds more", "almost always"),
        ("manner_humor", "Manner line + humour switch on", "backend/jarvis_manner.py:103, :110",
         manner_humor, "only when the owner turned humour on", "when humour is on"),
        ("spoken", "Spoken-answer note", "backend/jarvis_agent.py:7745", spoken,
         "a spoken turn", "spoken turns"),
        ("live", "Jarvis Live note", "backend/jarvis_live.py:576", live,
         "a Live conversation", "Live turns"),
        ("focus", "Focus-session note", "backend/jarvis_agent.py:7959", focus,
         "while a focus session runs", "focus turns"),
        ("cut_off", "Cut-off answer note (longest)", "backend/jarvis_agent.py:8069, CUT_OFF_MAX=240",
         cut_off, f"worst case: {cut_max} characters quoted back", "when the owner interrupted"),
        ("crisis", "Crisis help line", "backend/jarvis_wellbeing.py:174", crisis,
         "no tools are offered on this turn", "a crisis turn"),
        ("next_time", "Next-time reminder note (one reminder)", "backend/jarvis_next_time.py:323",
         next_note, "grows with each reminder; variable, not fixed", "when a reminder is due"),
        ("outside", "Outside-text note", "backend/jarvis_agent.py:5113, inserted at :9679", outside,
         "once any tool has run this turn", "after a tool runs"),
        ("dropped", "Prompt-dropped notice", "backend/jarvis_agent.py:4202", dropped,
         "only after an overflow was detected", "after an overflow"),
    )
    for key, label, where, text, note, when in notes:
        if isinstance(text, str):
            _row(rows, key, label, where, chars=len(text), note=note, when=when)
        else:
            _row(rows, key, label, where,
                 note="NOT MEASURED - this note's text could not be read",
                 when=when, measured=False)

    # ---- 6. the two blocks the work order lists that are not in the tree --
    _row(rows, "skills", "Active skill instructions (SKILL.md)",
         "not in this tree", note="ABSENT IN TREE - not measured",
         when="never today", absent=True)
    _row(rows, "project_workspace", "Project workspace block (<project_workspace>)",
         "not in this tree", note="ABSENT IN TREE - not measured",
         when="never today", absent=True)
    return rows


# ---------------------------------------------------------------------------
#   Totals
# ---------------------------------------------------------------------------


def _e3(rows, key):
    for row in rows:
        if row["key"] == key and row.get("measured") and row.get("e3") is not None:
            return row["e3"]
    return 0


def totals(rows, max_tokens: int) -> dict:
    """Three assembled stacks, each built from the rows above and nothing else.

    Only blocks that can really share a turn are added. A crisis turn offers
    no tools at all (``jarvis_agent.py:9062``, "No tools offered on a crisis
    turn"), so it is its own case rather than part of the tool-heavy worst.

    ``incomplete`` names the blocks a total needed but could not measure, so a
    reader can never mistake a floor for the stack.
    """
    persona = _e3(rows, "persona") + _e3(rows, "template")
    manner = _e3(rows, "manner")
    memory = _e3(rows, "pinned") + _e3(rows, "recalled")
    core = _e3(rows, "tools_core")
    ordinary = persona + manner + memory + core + max_tokens
    worst = (persona + manner + memory
             + _e3(rows, "spoken") + _e3(rows, "live") + _e3(rows, "focus")
             + _e3(rows, "cut_off") + _e3(rows, "outside")
             + _e3(rows, "tools_more") + max_tokens)
    drafting = worst + _e3(rows, "voiceprint_worst")
    crisis = persona + manner + _e3(rows, "crisis") + max_tokens
    needed = ("persona", "template", "manner", "pinned", "recalled", "tools_core",
              "tools_more", "spoken", "live", "focus", "cut_off", "outside",
              "voiceprint_worst", "crisis")
    incomplete = [row["key"] for row in rows
                  if row["key"] in needed and not row.get("measured")]
    return {"ordinary": ordinary, "worst": worst, "drafting": drafting,
            "crisis": crisis, "max_tokens": max_tokens,
            "with_more_tools": _e3(rows, "tools_more"),
            "incomplete": incomplete}


# ---------------------------------------------------------------------------
#   Structural drift - the only thing --check enforces
# ---------------------------------------------------------------------------


def structural_drift(src: Source, names: list) -> tuple:
    """(drift descriptions, notes). Nothing here is a token-size judgement.

    The recorded catalogue size is a statement about THIS repository's
    ``backend/``. Measuring another folder with ``--backend`` (a test fixture,
    a live install) checks that folder's comments against its own catalogue and
    says so in a note, because the recorded number would be a claim about a
    tree that was not measured.
    """
    drift, notes = [], []
    count = len(names)
    in_repo = Path(src.backend).resolve() == (REPO / "backend").resolve()
    if count != TOOL_COUNT_MEASURED:
        if in_repo:
            drift.append(
                f"the catalogue holds {count} tools; this tool recorded "
                f"{TOOL_COUNT_MEASURED} on {TOOL_COUNT_AT}. Re-measure the table in "
                f"docs/REVIEW-1-PROMPT-STACK-MEASURED-2026-10-23.md and set "
                f"TOOL_COUNT_MEASURED to {count}.")
        else:
            notes.append(
                f"this backend holds {count} tools; the recorded count "
                f"({TOOL_COUNT_MEASURED}, {TOOL_COUNT_AT}) is about this repository's "
                f"backend/ and was not applied to another folder")
    found = 0
    for pattern, label in COUNT_CLAIMS:
        for match in pattern.finditer(src.agent_text()):
            found += 1
            claimed = int(match.group(1))
            line = src.agent_text()[:match.start()].count("\n") + 1
            if claimed != count:
                drift.append(
                    f"backend/jarvis_agent.py:{line} says {claimed} tools "
                    f"({label}); the catalogue holds {count}. That comment is "
                    f"finding F1 in docs/REVIEW-1-PROMPT-STACK-MEASURED-2026-10-23.md; "
                    f"the exact patch is in .dsh-scratch/DOC2-PROPOSALS/"
                    f"prompt-stack-proposals.md (agent scratch, not in a clone).")
    if not found:
        notes.append("no tool-count claim was found in jarvis_agent.py's comments, "
                     "so there was nothing to cross-check against the catalogue")
    return drift, notes


# ---------------------------------------------------------------------------
#   Output
# ---------------------------------------------------------------------------


def context_of(src: Source, asked) -> tuple:
    """(the window, where the number came from)."""
    if asked:
        return int(asked), "given on the command line (--context)"
    if src.agent is not None:
        value = getattr(src.agent, "DEFAULT_CONTEXT", None)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return int(value), "backend/jarvis_agent.py:3944 DEFAULT_CONTEXT"
    return FALLBACK_CONTEXT, "no DEFAULT_CONTEXT in the tree; 4096 assumed"


def _fmt(value):
    return "    -  " if value is None else f"{value:7,d}"


def print_table(out, src: Source, backend: Path, rows, context: int, context_from: str,
                sums: dict) -> None:
    width, where_width = 58, 50
    out.write("Jarvis prompt stack - ESTIMATES ONLY, from the shipped code\n")
    out.write(f"Read from : {backend}\n")
    if src.mode == "import":
        out.write("How       : imported jarvis_agent, and asked the shipped functions\n")
    else:
        out.write(f"How       : STATIC PARSE - the import failed ({src.why})\n")
        out.write("            only plain string constants and the TOOLS keys can be read this way;\n")
        out.write("            a block that needs a function says NOT MEASURED, and is never guessed\n")
    out.write("Counting  : E3 = estimate_tokens (chars//3 + 6/message, the repo's own)\n")
    out.write("            E4 = chars/4 - a second ESTIMATE, not a tokenizer count\n")
    unread = [name for name in src.tool_names() if name.startswith("?")]
    if unread:
        out.write(f"Names     : {len(unread)} tool name(s) could not be read statically "
                  f"({', '.join(unread)}); the COUNT still includes them\n")
    out.write("\n")
    out.write(f"{'Block'.ljust(width)} {'Where it is built'.ljust(where_width)} "
              f"{'chars':>7} {'E3':>7} {'E4':>7}  When\n")
    out.write("-" * (width + where_width + 30 + 24) + "\n")
    for row in rows:
        label = row["label"]
        out.write(f"{label[:width].ljust(width)} {row['where'][:where_width].ljust(where_width)} "
                  f"{_fmt(row['chars'])} {_fmt(row['e3'])} {_fmt(row['e4'])}  {row['when']}\n")
        if row.get("note"):
            out.write(f"{'':{width}} {'':{where_width}}   {row['note']}\n")
    out.write("\n")
    share = 100.0 * sums["worst"] / context if context else 0.0
    incomplete = list(sums.get("incomplete") or [])
    out.write("ASSEMBLED STACKS (estimated tokens, the rows above added up):\n")
    if incomplete:
        out.write(f"  INCOMPLETE: {len(incomplete)} block(s) in these totals could not be measured\n"
                  f"  ({', '.join(incomplete)}), so every total below is a FLOOR, not the stack.\n")
    stacks = (
        (f"a usual turn   (rules, manner, memory recalling, 8 core tools, "
         f"{sums['max_tokens']:,} answer)", sums["ordinary"]),
        ("worst w/ tools (every note that can stack, all tools + more_tools)", sums["worst"]),
        ("worst, drafting (+ the worst voiceprint block)", sums["drafting"]),
        ("a crisis turn   (no tools are offered at all)", sums["crisis"]),
    )
    pad = max(len(item[0]) for item in stacks) + 2
    for label, value in stacks:
        out.write(f"  {label:<{pad}} {value:7,d}\n")
    out.write("\n")
    out.write(f"THE WINDOW: {context:,} tokens ({context_from}).\n")
    out.write(f"  the worst stack is {'at least ' if incomplete else ''}{share:.1f}% of it, before "
              f"one word of conversation or one tool result.\n")
    if sums["worst"] > context:
        out.write("  This does NOT fit: Ollama drops the oldest text of the prompt without saying\n"
                  "  so, and the answer is then drawn from a conversation the model no longer has.\n")
    elif share > 75:
        out.write("  Less than a quarter of the window is left for the conversation and tool output.\n")
    else:
        out.write(f"  That leaves {'at most ' if incomplete else ''}"
                  f"{context - sums['worst']:,} estimated tokens for the conversation\n"
                  "  and tool output.\n")
    out.write("  The repository disagrees about this window, so check which one is running:\n")
    for where, what in WINDOW_SOURCES:
        out.write(f"    {where:42s} {what}\n")
    out.write("\n")
    out.write("  These are estimates from characters (chars//3 and chars/4), not a tokenizer\n")
    out.write("  count. The only real numbers are Ollama's own prompt_eval_count rows in\n")
    out.write("  speed.jsonl - see the review doc for the two commands that settle it.\n")
    out.write("\n")
    schema_note = ""
    if sums.get("with_more_tools"):
        schema_note = (" The tool schemas\n"
                       f"({sums['with_more_tools']:,} estimated tokens) are the biggest block on every turn.")
    out.write(f"WHAT THIS MEANS: {'at least ' if incomplete else ''}about {sums['ordinary']:,} estimated "
              f"tokens on an ordinary turn and\n"
              f"about {sums['worst']:,} in the worst case, against a {context:,}-token window -\n")
    if sums["worst"] > context:
        out.write("so the worst case is bigger than the window, and the fix belongs on the tool side\n"
                  "(the schema list), because the tool schemas are the biggest block on every turn.\n")
    elif incomplete:
        out.write("so these totals are a floor: the blocks marked NOT MEASURED would add to them.\n")
    else:
        out.write(f"{100.0 * sums['worst'] / context:.1f}% of it before any conversation."
                  f"{schema_note}\n")


def to_json(src: Source, backend: Path, rows, context: int, context_from: str, sums: dict) -> dict:
    return {
        "tool": "tools/measure_prompt_stack.py",
        "generated_for": "Review #1 (10-Review Playbook), work order 2026-10-23 section 1",
        "backend": str(backend),
        "mode": src.mode,
        "import_error": src.why or None,
        "estimator": {
            "E3": "estimate_tokens: chars//3, plus 6 tokens a message (the repo's own)",
            "E4": "chars/4, a second estimate",
            "warning": "both are ESTIMATES from characters; neither is a tokenizer count",
        },
        "context": {"tokens": context, "from": context_from,
                    "disagreement": [{"where": w, "what": t} for w, t in WINDOW_SOURCES]},
        "blocks": rows,
        "totals": sums,
        "unread_tool_names": [n for n in src.tool_names() if n.startswith("?")],
        "structural_check": {
            "tool_count": len(src.tool_names()),
            "recorded_count": TOOL_COUNT_MEASURED,
            "recorded_on": TOOL_COUNT_AT,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure Jarvis's per-turn prompt stack, from the shipped code.")
    parser.add_argument("--backend", default=str(DEFAULT_BACKEND),
                        help="the backend folder to read (default: this repository's backend/)")
    parser.add_argument("--json", action="store_true", help="print the same numbers for a machine")
    parser.add_argument("--context", type=int, default=0,
                        help="the context window to report a share of (default: DEFAULT_CONTEXT)")
    parser.add_argument("--check", action="store_true",
                        help="structural drift only: the catalogue against its comments")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    backend = Path(args.backend).resolve()
    if not (backend / "jarvis_agent.py").is_file():
        sys.stderr.write(
            f"nothing to measure: {backend} has no jarvis_agent.py.\n"
            f"Point --backend at a backend folder (this repository's is {DEFAULT_BACKEND}).\n")
        return 2

    src = Source(backend)
    rows = build_rows(src)
    names = src.tool_names()
    max_tokens = 1024
    if src.agent is not None:
        max_tokens = int(getattr(src.agent, "DEFAULT_MAX_TOKENS", max_tokens))
    context, context_from = context_of(src, args.context)
    sums = totals(rows, max_tokens)

    if args.check:
        drift, notes = structural_drift(src, names)
        print(f"measuring {backend}")
        for note in notes:
            print(f"note  {note}")
        if drift:
            for line in drift:
                print(f"DRIFT {line}")
            print(f"\nFAIL: {len(drift)} structural drift(s) - the code's own numbers do not "
                  f"match the catalogue.")
            return 1
        print(f"ok    the catalogue holds {len(names)} tools and every count written in "
              f"jarvis_agent.py's comments agrees")
        return 0

    if args.json:
        print(json.dumps(to_json(src, backend, rows, context, context_from, sums),
                         indent=2, ensure_ascii=False))
        return 0

    print_table(sys.stdout, src, backend, rows, context, context_from, sums)
    return 0


if __name__ == "__main__":
    sys.exit(main())
